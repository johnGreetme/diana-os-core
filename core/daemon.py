import os
import json
import logging
import sys
import time
import sqlite3
import psutil
import tempfile
import io
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

# Add diana_core to sys.path so we can import skills correctly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

# Import TOTP logic
from skills.diana_core import secure_evaluator

# Parsers for Vision and Voice
from parsers.acoustic import AcousticParser
from parsers.optic import OpticParser

# Singleton parser instances
acoustic_parser = AcousticParser()
optic_parser = OpticParser(model_name="moondream")

SYS_LOCK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".sys_lock")
SESSION_WINDOW_MINUTES = 15

# 1. Load Master Configuration
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openclaw.json")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

BOT_TOKEN = config["telegram_gateway"]["bot_token"]
ADMIN_ID = config["telegram_gateway"]["admin_allowlist_id"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ----------------- VISION HANDLERS -----------------
async def handle_screen_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered by /screen [optional prompt]"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return
    
    status_msg = await update.message.reply_text("📸 Capturing primary monitor...")
    custom_prompt = " ".join(context.args) if context.args else "Describe what is visible on this desktop screen."

    try:
        image_bytes = optic_parser.capture_screen()
        await status_msg.edit_text("👁️ Analyzing screen with Moondream...")
        analysis = optic_parser.analyze_frame(image_bytes, prompt=custom_prompt)
        await update.message.reply_photo(
            photo=io.BytesIO(image_bytes),
            caption=f"🖥️ **Screen Analysis**\n\n{analysis}",
            parse_mode="Markdown"
        )
        await status_msg.delete()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Screen capture failed: {e}")
        await status_msg.edit_text(f"❌ Error during screen analysis: {e}")


async def handle_webcam_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Triggered by /webcam [optional prompt]"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return
    
    status_msg = await update.message.reply_text("📷 Opening webcam feed...")
    custom_prompt = " ".join(context.args) if context.args else "Describe the person or environment in this photo."

    try:
        image_bytes = optic_parser.capture_webcam()
        await status_msg.edit_text("👁️ Analyzing webcam frame with Moondream...")
        analysis = optic_parser.analyze_frame(image_bytes, prompt=custom_prompt)
        await update.message.reply_photo(
            photo=io.BytesIO(image_bytes),
            caption=f"📷 **Webcam Analysis**\n\n{analysis}",
            parse_mode="Markdown"
        )
        await status_msg.delete()
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Webcam capture failed: {e}")
        await status_msg.edit_text(f"❌ Error during webcam analysis: {e}")

def register_vision_handlers(app) -> None:
    """Registers optic commands with the Telegram application router."""
    app.add_handler(CommandHandler("screen", handle_screen_command))
    app.add_handler(CommandHandler("webcam", handle_webcam_command))
# ---------------------------------------------------

# ----------------- VOICE HANDLER -----------------
async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processes push-to-talk voice notes received via Telegram."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        logging.warning(f"[FIREWALL DROP] Unauthorized voice packet received from Telegram ID: {user_id}")
        return

    voice = update.message.voice
    if not voice:
        return

    status_msg = await update.message.reply_text("🎙️ Processing voice command via local Whisper (int8)...")

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        tg_file = await context.bot.get_file(voice.file_id)
        await tg_file.download_to_drive(tmp_path)

        transcribed_text = acoustic_parser.transcribe(tmp_path)

        if not transcribed_text:
            await status_msg.edit_text("⚠️ Could not transcribe audio or message was silent.")
            return

        await status_msg.edit_text(f"🗣️ **Transcribed:** *\"{transcribed_text}\"*\n\n⚙️ Routing to AST Sieve...", parse_mode="Markdown")

        # Pass transcribed text into the primary execution loop
        from skills.diana_core.diana_mediator import handle_tool_call
        response_payload = handle_tool_call(transcribed_text)
        
        if isinstance(response_payload, dict) or isinstance(response_payload, list):
            output_str = json.dumps(response_payload, indent=2)
        else:
            output_str = str(response_payload)
            
        if len(output_str) > 4000:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt", encoding='utf-8') as out_tmp:
                out_tmp.write(output_str)
                out_tmp_path = out_tmp.name
            await update.message.reply_document(document=open(out_tmp_path, "rb"), filename="diana_voice_response.txt")
            os.remove(out_tmp_path)
        else:
            await update.message.reply_text(output_str)

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Voice processing error: {e}")
        await status_msg.edit_text(f"❌ Error processing voice payload: {e}")

    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
# ---------------------------------------------------

# 2. Define the Zero-Trust Intercept Handler for Text
async def handle_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        logging.warning(f"[FIREWALL DROP] Unauthorized packet received from Telegram ID: {user_id}")
        return

    query_text = update.message.text
    logging.info(f"[+] Authorized Payload from Admin ({user_id}): {query_text}")

    # Evaluate Session TTL
    is_locked = True
    if os.path.exists(SYS_LOCK_FILE):
        mtime = os.path.getmtime(SYS_LOCK_FILE)
        if time.time() - mtime <= SESSION_WINDOW_MINUTES * 60:
            is_locked = False

    # 3. Check for TOTP Challenge Response
    if is_locked:
        if len(query_text.strip()) == 6 and query_text.strip().isdigit():
            token = query_text.strip()
            current_step = int(time.time()) // secure_evaluator.TOTP_INTERVAL
            valid_tokens = [
                secure_evaluator._generate_totp(secure_evaluator.TOTP_SECRET, current_step),
                secure_evaluator._generate_totp(secure_evaluator.TOTP_SECRET, current_step - 1),
            ]
            if token in valid_tokens:
                Path(SYS_LOCK_FILE).touch()
                logging.info("[TOTP] Valid token received. System UNLOCKED for 15 minutes.")
                await update.message.reply_text("🔓 *System Unlocked.* Session TTL set to 15 minutes.", parse_mode="Markdown")
                return
            else:
                logging.warning(f"[TOTP] Invalid token provided: {token}")
                return
        else:
            logging.warning("[SIEVE GATE] System is HARD-LOCKED. Payload dropped silently.")
            return

    # 4. Route standard prompts to the neuro-symbolic mediator
    try:
        from skills.diana_core.diana_mediator import handle_tool_call
        await update.message.reply_text("🧠 *D.I.A.N.A. Mediator Processing...*", parse_mode="Markdown")
        response_payload = handle_tool_call(query_text)
        
        if isinstance(response_payload, dict) or isinstance(response_payload, list):
            output_str = json.dumps(response_payload, indent=2)
        else:
            output_str = str(response_payload)
            
        if len(output_str) > 4000:
            with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt", encoding='utf-8') as tmp:
                tmp.write(output_str)
                tmp_path = tmp.name
            await update.message.reply_document(document=open(tmp_path, "rb"), filename="diana_response.txt")
            os.remove(tmp_path)
        else:
            await update.message.reply_text(output_str)
        
    except Exception as e:
        error_msg = f"⚠️ Mediator Execution Fault: {str(e)}"
        logging.error(error_msg)
        await update.message.reply_text(error_msg)

# 5. Background Heartbeat Tasks
def get_vram_usage():
    try:
        import subprocess
        result = subprocess.run(['nvidia-smi', '--query-gpu=memory.used,memory.total', '--format=csv,nounits,noheader'], stdout=subprocess.PIPE, text=True)
        return result.stdout.strip()
    except:
        return "VRAM monitoring unavailable (nvidia-smi not found)"

def get_recent_sieve_failures():
    fail_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Reflections", "failed_geometries.md")
    if os.path.exists(fail_log):
        with open(fail_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
            return "".join(lines[-20:])
    return "No recent failures."

async def send_telegram_heartbeat(context: ContextTypes.DEFAULT_TYPE):
    uptime_sec = time.time() - psutil.boot_time()
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    uptime_str = f"{int(days)}d {int(hours)}h {int(mins)}m" if days > 0 else f"{int(hours)}h {int(mins)}m"
    
    is_locked = True
    if os.path.exists(SYS_LOCK_FILE):
        mtime = os.path.getmtime(SYS_LOCK_FILE)
        if time.time() - mtime <= SESSION_WINDOW_MINUTES * 60:
            is_locked = False
            
    lock_status = "🔓 UNLOCKED" if not is_locked else "🔒 HARD-LOCKED"
    
    msg = f"🟢 *D.I.A.N.A. Uptime Heartbeat*\nHost Uptime: {uptime_str}\nSystem Status: {lock_status}"
    
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
        logging.info("[HEARTBEAT] Telegram status sent.")
        
        # Grounded Agentic Heartbeat
        if not is_locked:
            vram_stat = get_vram_usage()
            sieve_log = get_recent_sieve_failures()
            
            grounded_prompt = f"""HEARTBEAT TICK. You have just woken up autonomously. 
[SYSTEM TELEMETRY]:
VRAM Allocation: {vram_stat} MB
Host Uptime: {uptime_str}

[RECENT AST SIEVE FAILURES (LAST 20 LINES)]:
{sieve_log}

Check the system status based on this real telemetry. If there are recent logical failures in the AST sieve, analyze them. Summarize your findings and report on local node health. Surprise me with an insight or action based on this real data. Do not hallucinate data."""

            from skills.diana_core.diana_mediator import handle_tool_call
            response_payload = handle_tool_call(grounded_prompt)
            
            if isinstance(response_payload, dict) or isinstance(response_payload, list):
                output_str = json.dumps(response_payload, indent=2)
            else:
                output_str = str(response_payload)
            
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧠 *Agentic Heartbeat Synthesis:*\n{output_str}", parse_mode="Markdown")

    except Exception as e:
        logging.error(f"[HEARTBEAT] Failed to send Telegram status: {e}")

async def write_log_checkpoint(context: ContextTypes.DEFAULT_TYPE):
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Reflections", "deflections.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            entry = {
                "timestamp": ts,
                "rule": "HEARTBEAT",
                "status": "HEALTHY",
                "rationale": "System Checkpoint: Daemon is online",
                "prompt": "N/A",
                "payload": "N/A"
            }
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logging.error(f"[HEARTBEAT] Log checkpoint failed: {e}")

# 6. SQLite-Backed Scheduled Task Executor
LEDGER_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Reflections", "semantic_ledger.db")

async def execute_due_scheduled_tasks(context: ContextTypes.DEFAULT_TYPE):
    """
    Polls the scheduled_tasks table for any tasks where execute_at <= now AND status = 'pending'.
    Executes due tasks by injecting their prompts into handle_tool_call and sends results to Telegram.
    This function is crash-safe: tasks persist in SQLite across daemon restarts and host reboots.
    """
    from datetime import datetime
    
    try:
        conn = sqlite3.connect(LEDGER_DB_PATH)
        cursor = conn.cursor()
        
        # Ensure table exists (first-run safety)
        cursor.execute('''CREATE TABLE IF NOT EXISTS scheduled_tasks
               (id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_prompt TEXT NOT NULL,
                execute_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending','completed','failed')))''')
        
        now_iso = datetime.now().isoformat()
        cursor.execute(
            "SELECT id, task_prompt, execute_at FROM scheduled_tasks WHERE status = 'pending' AND execute_at <= ?",
            (now_iso,)
        )
        due_tasks = cursor.fetchall()
        conn.close()
        
        if not due_tasks:
            return
        
        logging.info(f"[SCHEDULER] Found {len(due_tasks)} due task(s). Executing...")
        
        for task_id, task_prompt, execute_at in due_tasks:
            logging.info(f"[SCHEDULER] Executing Task #{task_id}: {task_prompt[:80]}...")
            
            try:
                from skills.diana_core.diana_mediator import handle_tool_call
                response_payload = handle_tool_call(task_prompt)
                
                if isinstance(response_payload, dict) or isinstance(response_payload, list):
                    output_str = json.dumps(response_payload, indent=2)
                else:
                    output_str = str(response_payload)
                
                # Mark as completed
                conn = sqlite3.connect(LEDGER_DB_PATH)
                conn.execute("UPDATE scheduled_tasks SET status = 'completed' WHERE id = ?", (task_id,))
                conn.commit()
                conn.close()
                
                # Send result to admin via Telegram
                header = f"⏰ *Scheduled Task #{task_id} Executed*\n📝 Prompt: _{task_prompt[:100]}_\n\n"
                full_msg = header + output_str
                
                if len(full_msg) > 4000:
                    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt", encoding='utf-8') as tmp:
                        tmp.write(full_msg)
                        tmp_path = tmp.name
                    await context.bot.send_message(chat_id=ADMIN_ID, text=header + "(Response attached as file)", parse_mode="Markdown")
                    await context.bot.send_document(chat_id=ADMIN_ID, document=open(tmp_path, "rb"), filename=f"scheduled_task_{task_id}.txt")
                    os.remove(tmp_path)
                else:
                    await context.bot.send_message(chat_id=ADMIN_ID, text=full_msg, parse_mode="Markdown")
                
                logging.info(f"[SCHEDULER] Task #{task_id} completed successfully.")
                
            except Exception as e:
                logging.error(f"[SCHEDULER] Task #{task_id} failed: {e}")
                # Mark as failed
                try:
                    conn = sqlite3.connect(LEDGER_DB_PATH)
                    conn.execute("UPDATE scheduled_tasks SET status = 'failed' WHERE id = ?", (task_id,))
                    conn.commit()
                    conn.close()
                except:
                    pass
                
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ *Scheduled Task #{task_id} Failed*\nPrompt: _{task_prompt[:100]}_\nError: {str(e)}",
                    parse_mode="Markdown"
                )
    
    except Exception as e:
        logging.error(f"[SCHEDULER] Scheduled task executor error: {e}")

async def daily_3am_cron(context: ContextTypes.DEFAULT_TYPE):
    uptime_sec = time.time() - psutil.boot_time()
    days, rem = divmod(uptime_sec, 86400)
    hours, rem = divmod(rem, 3600)
    mins, _ = divmod(rem, 60)
    uptime_str = f"{int(days)}d {int(hours)}h {int(mins)}m" if days > 0 else f"{int(hours)}h {int(mins)}m"
    
    msg = f"🌙 *D.I.A.N.A. Nightly Cron (3:00 AM)*\nHost Uptime: {uptime_str}\nStatus: Autonomous Wakeup"
    
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode="Markdown")
        logging.info("[CRON] 3 AM Nightly status sent.")
        
        vram_stat = get_vram_usage()
        sieve_log = get_recent_sieve_failures()
        
        grounded_prompt = f"""NIGHTLY CRON TICK (3:00 AM). You have just woken up autonomously for your nightly maintenance. 
[SYSTEM TELEMETRY]:
VRAM Allocation: {vram_stat} MB
Host Uptime: {uptime_str}

[RECENT AST SIEVE FAILURES (LAST 20 LINES)]:
{sieve_log}

Perform your nightly maintenance routine. Review any logic failures, verify your temporal ledger, and summarize the state of the host system. Surprise me with an insight or action based on this real data. Do not hallucinate data."""

        from skills.diana_core.diana_mediator import handle_tool_call
        response_payload = handle_tool_call(grounded_prompt)
        
        if isinstance(response_payload, dict) or isinstance(response_payload, list):
            output_str = json.dumps(response_payload, indent=2)
        else:
            output_str = str(response_payload)
        
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧠 *Nightly Maintenance Synthesis:*\n{output_str}", parse_mode="Markdown")

    except Exception as e:
        logging.error(f"[CRON] Failed to execute 3 AM cron: {e}")

# 7. Initialize Asynchronous Long-Polling Loop
if __name__ == "__main__":
    logging.info("[+] Launching Kytin OpenClaw Telegram Gateway Daemon...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Bind text handler
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_incoming_message))
    # Bind voice handler
    app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
    
    # Register vision handlers (/screen, /webcam)
    register_vision_handlers(app)
    
    # Schedule Heartbeats and Temporal Task Executor
    if app.job_queue:
        import datetime
        # Daily 3 AM Nightly Cron
        app.job_queue.run_daily(daily_3am_cron, time=datetime.time(hour=3, minute=0, second=0))
        
        # Send Telegram heartbeat every 12 hours
        app.job_queue.run_repeating(send_telegram_heartbeat, interval=43200, first=10)
        # Write to log every 10 minutes
        app.job_queue.run_repeating(write_log_checkpoint, interval=600, first=5)
        # Poll for due scheduled tasks every 30 seconds
        app.job_queue.run_repeating(execute_due_scheduled_tasks, interval=30, first=15)
        logging.info("[+] Heartbeat jobs and Temporal Task Executor scheduled.")
    else:
        logging.warning("[-] JobQueue not available. Heartbeats and scheduling disabled.")
    
    # Start long-polling
    app.run_polling(poll_interval=1.0)

