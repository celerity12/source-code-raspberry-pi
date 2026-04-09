#!/usr/bin/env python3
"""
Gemini-powered agent for Pi-hole Analytics + Telegram.

Spawns the MCP server as a subprocess, translates MCP tool definitions into
Gemini function declarations, and runs a full agentic loop — Gemini decides
which tools to call, this agent executes them and feeds results back.

Usage:
    python llm/gemini_agent.py
    python llm/gemini_agent.py --prompt "What devices are on my network?"
    python llm/gemini_agent.py --watch          # monitor & alert mode

Layer: LLM — Gemini agentic loop only.
Spawns mcp/server.py as a subprocess; knows nothing about connectors directly.
"""

import asyncio
import json
import logging
import re
import sys
import argparse
import time
from collections import deque
from pathlib import Path
from datetime import datetime

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).parent.parent))
from config.loader import load_llm, load_prompts, load_connector
from connectors.telegram_client import TelegramClient

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [Gemini] %(levelname)s %(message)s')

_SERVER = Path(__file__).parent.parent / 'mcp' / 'server.py'


def _mcp_to_gemini_tool(mcp_tool) -> genai.protos.Tool:
    """Convert an MCP Tool definition into a Gemini FunctionDeclaration."""
    schema = mcp_tool.inputSchema or {}
    props  = schema.get('properties', {})
    req    = schema.get('required', [])

    parameters = genai.protos.Schema(
        type        = genai.protos.Type.OBJECT,
        properties  = {
            k: genai.protos.Schema(
                type        = _map_type(v.get('type', 'string')),
                description = v.get('description', ''),
                enum        = v.get('enum', []) or [],
            )
            for k, v in props.items()
        },
        required = req,
    )

    fn_decl = genai.protos.FunctionDeclaration(
        name        = mcp_tool.name,
        description = mcp_tool.description or '',
        parameters  = parameters,
    )
    return genai.protos.Tool(function_declarations=[fn_decl])


def _map_type(t: str) -> genai.protos.Type:
    return {
        'string':  genai.protos.Type.STRING,
        'integer': genai.protos.Type.INTEGER,
        'number':  genai.protos.Type.NUMBER,
        'boolean': genai.protos.Type.BOOLEAN,
        'array':   genai.protos.Type.ARRAY,
        'object':  genai.protos.Type.OBJECT,
    }.get(t, genai.protos.Type.STRING)


# ── Core agent ────────────────────────────────────────────────────────────────

class PiholeGeminiAgent:
    """
    Gemini agent with Pi-hole + Telegram tools via MCP.

    Lifecycle:
        async with PiholeGeminiAgent(cfg) as agent:
            reply = await agent.chat("What's on my network?")
    """

    # Paid-tier limits for gemini-2.0-flash
    _RPM_LIMIT = 2000     # requests per minute
    _RPD_LIMIT = 0        # unlimited (0 = skip RPD tracking)
    _MAX_RETRIES = 3      # retries on ResourceExhausted before giving up

    def __init__(self):
        self._llm_cfg  = load_llm()
        self._prompts  = load_prompts()
        self.session: ClientSession = None
        self.model   = None
        self.tools   = []
        self.history = []
        # API call tracking — stores Unix timestamps of each Gemini call
        self._calls_minute: deque = deque()   # last 60s window
        self._total_calls   = 0

    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, *_):
        pass

    async def _connect(self):
        """Spawn the MCP server and initialise the Gemini model."""
        # ── MCP connection ────────────────────────────────────────────────────
        server_params = StdioServerParameters(
            command = sys.executable,
            args    = [str(_SERVER)],
        )
        self._transport = stdio_client(server_params)
        read, write = await self._transport.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()

        # Fetch tool list from MCP server
        tools_result = await self.session.list_tools()
        self.tools   = tools_result.tools
        log.info("MCP server ready — %d tools available", len(self.tools))

        # ── Gemini model ──────────────────────────────────────────────────────
        genai.configure(api_key=self._llm_cfg['api_key'])
        gemini_tools = [_mcp_to_gemini_tool(t) for t in self.tools]

        system_prompt = self._prompts.get('system_prompt', _SYSTEM_PROMPT_FALLBACK)
        self.model = genai.GenerativeModel(
            model_name         = self._llm_cfg.get('model', 'gemini-2.0-flash'),
            tools              = gemini_tools,
            system_instruction = system_prompt.strip(),
        )
        self.chat_session = self.model.start_chat(history=[])
        log.info("Gemini model ready: %s", self._llm_cfg.get('model'))

    def _record_api_call(self):
        """Record a Gemini API call timestamp and prune expired entries."""
        now = time.time()
        self._calls_minute.append(now)
        self._total_calls += 1
        while self._calls_minute and now - self._calls_minute[0] > 60:
            self._calls_minute.popleft()

    def _wait_suggestion(self) -> str:
        """Return a short warning if approaching RPM limit, else empty string."""
        now = time.time()
        while self._calls_minute and now - self._calls_minute[0] > 60:
            self._calls_minute.popleft()
        rpm_used = len(self._calls_minute)
        rpm_left = self._RPM_LIMIT - rpm_used
        if rpm_left <= 0 and self._calls_minute:
            wait_secs = max(1, int(60 - (now - self._calls_minute[0])) + 1)
            return f"\n\n⏳ Rate limit reached — wait ~{wait_secs}s."
        return ""

    async def _send_with_retry(self, payload):
        """Send a message to Gemini, retrying on ResourceExhausted with backoff."""
        last_exc = None
        for attempt in range(self._MAX_RETRIES):
            try:
                self._record_api_call()
                return self.chat_session.send_message(payload)
            except ResourceExhausted as exc:
                last_exc = exc
                m = re.search(r'retry[^\d]*(\d+)', str(exc))
                wait = int(m.group(1)) if m else (5 * (attempt + 1))
                log.warning("Gemini rate limit (attempt %d/%d) — sleeping %ds: %s",
                            attempt + 1, self._MAX_RETRIES, wait, exc)
                await asyncio.sleep(wait)
        raise RuntimeError(
            f"🚫 Gemini rate limit after {self._MAX_RETRIES} retries. "
            f"Try again in a moment."
        ) from last_exc

    async def _call_tool(self, name: str, args: dict) -> str:
        """Call an MCP tool and return the result as a string."""
        log.info("→ Calling tool: %s(%s)", name, json.dumps(args))
        result = await self.session.call_tool(name, args)
        if result.isError:
            content = f"ERROR: {result.content[0].text if result.content else 'unknown'}"
        else:
            content = result.content[0].text if result.content else '{}'
        log.info("← Tool result: %s...", content[:120])
        return content

    async def chat(self, user_message: str) -> str:
        """
        Send a message and run the full agentic loop until Gemini stops
        calling tools and produces a final text response.
        """
        log.info("User: %s", user_message)
        response = await self._send_with_retry(user_message)

        # Agentic loop: keep going while Gemini is calling tools
        while True:
            # Collect all function calls in this response
            fn_calls = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if part.function_call.name
            ]

            if not fn_calls:
                break  # Gemini produced a final text response — done

            # Execute all tool calls and collect results
            tool_results = []
            for fn_call in fn_calls:
                result_text = await self._call_tool(
                    fn_call.name,
                    dict(fn_call.args),
                )
                tool_results.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name     = fn_call.name,
                            response = {"result": result_text},
                        )
                    )
                )

            # Feed results back to Gemini
            response = await self._send_with_retry(tool_results)

        # Extract final text response
        text_parts = [
            part.text
            for candidate in response.candidates
            for part in candidate.content.parts
            if hasattr(part, 'text') and part.text
        ]
        reply = '\n'.join(text_parts).strip()
        log.info("Agent reply: %s...", reply[:120])
        return reply

    async def run_interactive(self):
        """Interactive REPL loop."""
        print("\n🛡️  Pi-hole Analytics + Telegram — Gemini Agent")
        print("   Type your question or 'quit' to exit.\n")
        while True:
            try:
                user = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break
            if not user:
                continue
            if user.lower() in ('quit', 'exit', 'q'):
                break
            reply = await self.chat(user)
            print(f"\nAgent: {reply}\n")

    async def run_watch_mode(self, interval_minutes: int = None):
        """
        Monitor mode: every interval_minutes, check for alerts and send
        a Telegram notification if anything is found.

        Skips checks during the quiet window (skip_start_hour to skip_end_hour).
        During the quiet window, sleeps until the window ends before checking again.

        Config (config/llm/prompts.yaml):
          watch_interval_minutes: 360
          watch_skip_start_hour:  4    # 4 AM
          watch_skip_end_hour:    10   # 10 AM
        """
        interval    = interval_minutes or self._prompts.get('watch_interval_minutes', 360)
        skip_start  = self._prompts.get('watch_skip_start_hour', 4)
        skip_end    = self._prompts.get('watch_skip_end_hour', 10)
        prompt      = self._prompts.get('watch_prompt', _WATCH_PROMPT_FALLBACK).strip()
        print(f"Watch mode — every {interval} min, skipping {skip_start:02d}:00–{skip_end:02d}:00. Ctrl+C to stop.")

        # Wait the full interval before the first check so startup doesn't
        # immediately burn a Gemini call (especially important on restart loops).
        print(f"[{datetime.now():%H:%M}] Watch mode started — first check in {interval} min.")
        await asyncio.sleep(interval * 60)

        while True:
            try:
                now  = datetime.now()
                hour = now.hour

                if skip_start <= hour < skip_end:
                    wake = now.replace(hour=skip_end, minute=0, second=0, microsecond=0)
                    secs = (wake - now).total_seconds()
                    print(f"[{now:%H:%M}] Quiet window ({skip_start:02d}:00–{skip_end:02d}:00) — sleeping {int(secs//60)} min until {skip_end:02d}:00.")
                    await asyncio.sleep(secs)
                    continue

                reply = await self.chat(prompt)
                print(f"[{datetime.now():%H:%M}] {reply}")

            except (RuntimeError, Exception) as exc:
                # Catch quota errors and other failures — log and sleep, don't crash
                log.warning("Watch check failed: %s — sleeping %d min before retry.", exc, interval)

            await asyncio.sleep(interval * 60)

        # (KeyboardInterrupt propagates up and is caught by asyncio.gather)


    async def run_telegram_mode(self, poll_interval: float = 3.0):
        """
        Telegram bot command mode — polls for incoming messages and responds via Gemini.

        Supported commands (send from Telegram):
          /status   — network overview
          /alerts   — security alerts today
          /health   — system health (disk, RAM, CPU, temp)
          /devices  — active devices today
          /block <domain>   — block a domain
          /unblock <domain> — unblock a domain
          /report   — trigger daily email report
          /help     — list available commands
          <anything else>   — answered by Gemini as natural language

        poll_interval: seconds between polling Telegram for new messages (default 3s)
        """
        tg_cfg  = load_connector('telegram')
        tg      = TelegramClient(
            bot_token       = tg_cfg['bot_token'],
            default_chat_id = str(tg_cfg['default_chat_id']),
        )

        # Map slash commands to minimal prompts for the agent
        COMMAND_PROMPTS = {
            '/status':  'Send network summary to Telegram.',
            '/alerts':  'Send security alerts to Telegram.',
            '/health':  'Send system health to Telegram.',
            '/devices': 'Send active devices list to Telegram.',
            '/report':  'Trigger daily email report.',
        }

        HELP_TEXT = (
            "🛡️ <b>Pi-hole Bot Commands</b>\n\n"
            "/status  — Network overview\n"
            "/alerts  — Security alerts today\n"
            "/health  — System health (disk, RAM, CPU, temp)\n"
            "/devices — Active devices today\n"
            "/block domain.com — Block a domain\n"
            "/unblock domain.com — Unblock a domain\n"
            "/report  — Trigger daily email report\n"
            "/help    — Show this message\n\n"
            "Or just ask anything in plain English."
        )

        bot_info = tg.get_me()
        bot_name = bot_info.get('username', 'pihole-bot')

        # Drain any pending messages accumulated while the bot was offline.
        # Set offset past all existing updates so we only handle NEW messages.
        pending = tg.get_updates(offset=None, limit=100)
        if pending:
            offset = pending[-1]['update_id'] + 1
            log.info("Skipped %d pending message(s) from before startup.", len(pending))
        else:
            offset = None

        print(f"Telegram bot @{bot_name} listening. Send /help in Telegram to start.")
        tg.send_message("🟢 <b>Pi-hole bot is online.</b> Send /help for commands.")

        while True:
            try:
                updates = tg.get_updates(offset=offset, limit=20)
                for update in updates:
                    offset = update['update_id'] + 1
                    msg = update.get('message') or update.get('edited_message')
                    if not msg:
                        continue
                    text    = (msg.get('text') or '').strip()
                    chat_id = str(msg['chat']['id'])
                    if not text:
                        continue

                    log.info("Telegram [%s]: %s", chat_id, text)

                    # /help — no Gemini call needed
                    if text.lower() == '/help':
                        tg.send_message(HELP_TEXT, chat_id=chat_id)
                        continue

                    # /block and /unblock — extract domain argument
                    if text.lower().startswith('/block '):
                        domain = text.split(None, 1)[1].strip()
                        prompt = f'Block "{domain}" and confirm via Telegram.'
                    elif text.lower().startswith('/unblock '):
                        domain = text.split(None, 1)[1].strip()
                        prompt = f'Unblock "{domain}" and confirm via Telegram.'
                    elif text.lower() in COMMAND_PROMPTS:
                        prompt = COMMAND_PROMPTS[text.lower()]
                    else:
                        # Natural language
                        prompt = f'User: "{text}". Reply via telegram_send_message to chat {chat_id}.'

                    # Run through Gemini agent and send reply
                    try:
                        tg.send_message("⏳ Checking...", chat_id=chat_id)
                        # Fresh session per message — no accumulated history eating tokens
                        self.chat_session = self.model.start_chat(history=[])
                        reply = await self.chat(prompt)
                        wait_note = self._wait_suggestion()
                        # If Gemini didn't already send via telegram_ tool, send the text reply
                        if reply and reply.strip().lower() not in ('', 'all clear', 'done'):
                            tg.send_message(reply + wait_note, chat_id=chat_id)
                        elif wait_note:
                            tg.send_message(wait_note.strip(), chat_id=chat_id)
                    except Exception as exc:
                        log.error("Agent error for [%s]: %s", text, exc)
                        tg.send_message(f"❌ Error: {exc}", chat_id=chat_id)

                await asyncio.sleep(poll_interval)

            except KeyboardInterrupt:
                tg.send_message("🔴 <b>Pi-hole bot going offline.</b>")
                print("\nTelegram bot stopped.")
                break
            except Exception as exc:
                log.error("Telegram poll error: %s", exc)
                await asyncio.sleep(10)  # back off on errors


# ── Fallback prompts (used only when config.yaml llm section is missing) ──────
# Primary source is config.yaml → llm.system_prompt / llm.watch_prompt

_SYSTEM_PROMPT_FALLBACK = """
You are a home network security assistant powered by Pi-hole Analytics.
Use pihole_ tools to query the network and telegram_ tools to notify the user.
Always interpret results in plain English — not raw JSON.
""".strip()

_WATCH_PROMPT_FALLBACK = (
    "Check Pi-hole for any security alerts or excessive usage right now. "
    "If there are alerts, send them to Telegram. "
    "If everything is fine, just say 'All clear'."
)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Pi-hole Gemini Agent")
    parser.add_argument('--prompt',   '-p', help="Single prompt (non-interactive)")
    parser.add_argument('--telegram', '-t', action='store_true',
                        help="Telegram bot mode: receive /commands and reply via Telegram")
    parser.add_argument('--watch',    '-w', action='store_true',
                        help="Watch mode: periodic alert checks sent to Telegram")
    parser.add_argument('--interval', type=int,
                        help="Watch mode interval in minutes (overrides prompts.yaml)")
    args = parser.parse_args()

    async with PiholeGeminiAgent() as agent:
        if args.prompt:
            reply = await agent.chat(args.prompt)
            print(reply)
        elif args.telegram and args.watch:
            # Run both concurrently: bot listens for commands + watch sends periodic alerts
            await asyncio.gather(
                agent.run_telegram_mode(),
                agent.run_watch_mode(interval_minutes=args.interval),
            )
        elif args.telegram:
            await agent.run_telegram_mode()
        elif args.watch:
            await agent.run_watch_mode(interval_minutes=args.interval)
        else:
            await agent.run_interactive()


if __name__ == "__main__":
    asyncio.run(main())
