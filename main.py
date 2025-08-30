import os
import discord
from discord.ext import commands
import asyncio
from keep_alive import keep_alive

import json
import aiofiles

# ---------- CONFIG ----------
# Bot configurations: {token_env_name: prefix}
BOT_CONFIGS = {
    "TOKEN": "$",  # Main bot with $ prefix
    "TOKEN2": "!",  # Second bot with ! prefix  
    "TOKEN3": "?",  # Third bot with ? prefix
    # Add more bots as needed: "TOKEN4": "&", etc.
}

ALLOWED_USERS = [
    1096838620712804405,
    1348330851263315968,
    1388657253451698306  # replace with your Discord user ID (int)
    # Add more user IDs here as needed
]
MIN_DELAY = 0.5  # seconds
MAX_AMOUNT = 20

# Global variables to track spam tasks and stop flags for all bots
spam_tasks = {}
stop_flags = {}
bots = {}
emergency_stop = False

# Auto-restart functionality
last_commands = {
}  # Track last command per user per bot: {f"{prefix}_{user_id}": command_data}
restart_tasks = {}  # Track restart attempts
MAX_RESTART_ATTEMPTS = 3
RESTART_DELAY = 5  # seconds to wait before restart

# Account generation system

generated_accounts = {}  # Store generated account data
generation_tasks = {}  # Track ongoing generation tasks
# ---------------------------


def store_last_command(prefix: str, user_id: int, command_type: str, **kwargs):
    """Store the last executed command for auto-restart"""
    key = f"{prefix}_{user_id}"
    last_commands[key] = {
        'command_type': command_type,
        'timestamp': asyncio.get_event_loop().time(),
        'attempts': 0,
        **kwargs
    }


async def restart_last_command(ctx, prefix: str, error_msg: str = None):
    """Restart the last command after an error"""
    user_id = ctx.author.id
    key = f"{prefix}_{user_id}"

    if key not in last_commands:
        return False

    command_data = last_commands[key]
    command_data['attempts'] += 1

    # Don't restart if too many attempts
    if command_data['attempts'] > MAX_RESTART_ATTEMPTS:
        try:
            await ctx.author.send(
                f"❌ Max restart attempts ({MAX_RESTART_ATTEMPTS}) reached for {prefix} bot. "
                f"Please manually restart the command if needed.")
        except:
            pass
        last_commands.pop(key, None)
        return False

    try:
        await ctx.author.send(
            f"🔄 Restarting command on {prefix} bot (attempt {command_data['attempts']}/{MAX_RESTART_ATTEMPTS})"
            f"{f' after error: {error_msg}' if error_msg else ''}...")
    except:
        pass

    # Wait before restart
    await asyncio.sleep(RESTART_DELAY)

    # Restart based on command type
    try:
        if command_data['command_type'] == 'send':
            # Recreate send command
            message = command_data['message']
            delay = command_data['delay']
            amount = command_data['amount']

            # Don't store again to avoid infinite loop
            await execute_send_command(ctx,
                                       message,
                                       delay,
                                       amount,
                                       store_command=False)

        elif command_data['command_type'] == 'spm':
            # Recreate spm command
            message = command_data['message']
            delay = command_data['delay']

            # Don't store again to avoid infinite loop
            await execute_spm_command(ctx,
                                      prefix,
                                      message,
                                      delay,
                                      store_command=False)

        return True

    except Exception as e:
        try:
            await ctx.author.send(
                f"❌ Failed to restart command on {prefix} bot: {e}")
        except:
            pass
        return False


async def execute_send_command(ctx,
                               message: str,
                               delay: float,
                               amount: int,
                               store_command: bool = True):
    """Execute the send command with optional command storage"""
    prefix = ctx.bot.command_prefix
    user_id = ctx.author.id

    # Store command for auto-restart
    if store_command:
        store_last_command(prefix,
                           user_id,
                           'send',
                           message=message,
                           delay=delay,
                           amount=amount)

    # Create a stop flag for this user
    stop_flags[user_id] = False

    # Send the repeated messages
    for i in range(amount):
        # Check if user requested to stop or emergency stop activated
        if stop_flags.get(user_id, False) or emergency_stop:
            # Send stop notification to user's DM
            try:
                if emergency_stop:
                    await ctx.author.send(
                        f"🚨 Emergency stop activated. Message sending stopped after {i} messages."
                    )
                else:
                    await ctx.author.send(
                        f"🛑 Message sending stopped after {i} messages.")
            except:
                pass
            break

        try:
            await ctx.send(message)
            # Don't sleep after the last message
            if i < amount - 1:
                await asyncio.sleep(delay)

        # ---- 503 resilience (do not die; wait + continue) ----
        except discord.errors.DiscordServerError as e:
            if getattr(e, "status", None) == 503:
                try:
                    await ctx.author.send(
                        f"⚠️ Discord server error (503). Retrying…")
                except:
                    pass
                await asyncio.sleep(3)
                continue
            else:
                try:
                    await ctx.author.send(
                        f"⚠️ Discord server error occurred: {e}")
                except:
                    pass
                # Try to restart on non-503 server errors
                if await restart_last_command(ctx, prefix, str(e)):
                    return
                break

        except discord.HTTPException as e:
            # Keep original DM, but if it's specifically 503, don't stop
            try:
                await ctx.author.send(f"⚠️ Discord API error occurred: {e}")
            except:
                pass
            if getattr(e, "status", None) == 503:
                await asyncio.sleep(3)
                continue
            # Try to restart on non-503 HTTP errors
            if await restart_last_command(ctx, prefix, str(e)):
                return
            break
        # ------------------------------------------------------

        except Exception as e:
            # Send error to user's DM
            try:
                await ctx.author.send(f"⚠️ Unexpected error occurred: {e}")
            except:
                pass
            # Try to restart on unexpected errors
            if await restart_last_command(ctx, prefix, str(e)):
                return
            break

    # Clean up the stop flag
    stop_flags.pop(user_id, None)

    # Clear last command on successful completion
    key = f"{prefix}_{user_id}"
    if key in last_commands and last_commands[key]['command_type'] == 'send':
        last_commands.pop(key, None)


async def spam_loop_with_restart(ctx, message: str, delay: float, prefix: str):
    """Continuous spam loop with restart capability"""
    global emergency_stop
    count = 0
    user_id = ctx.author.id

    try:
        while True:
            if emergency_stop:
                try:
                    await ctx.author.send(
                        f"🚨 Emergency stop activated. Spam stopped after {count} messages."
                    )
                except:
                    pass
                break

            # ---- 503 resilience inside spam loop ----
            try:
                await ctx.send(message)
                count += 1
            except discord.errors.DiscordServerError as e:
                if getattr(e, "status", None) == 503:
                    await asyncio.sleep(3)
                    continue
                else:
                    # Try to restart on non-503 server errors
                    if await restart_last_command(ctx, prefix, str(e)):
                        return
                    raise
            except discord.HTTPException as e:
                if getattr(e, "status", None) == 503:
                    await asyncio.sleep(3)
                    continue
                else:
                    # Try to restart on non-503 HTTP errors
                    if await restart_last_command(ctx, prefix, str(e)):
                        return
                    raise
            except Exception as e:
                # Try to restart on unexpected errors
                if await restart_last_command(ctx, prefix, str(e)):
                    return
                raise
            # -----------------------------------------

            await asyncio.sleep(delay)
    except asyncio.CancelledError:
        try:
            await ctx.author.send(f"🛑 Spam stopped after {count} messages.")
        except:
            pass
        # Clear last command on cancellation
        key = f"{prefix}_{user_id}"
        if key in last_commands and last_commands[key]['command_type'] == 'spm':
            last_commands.pop(key, None)
        raise
    except Exception as e:
        try:
            await ctx.author.send(f"⚠️ Spam error after {count} messages: {e}")
        except:
            pass
        raise


async def execute_spm_command(ctx,
                              prefix: str,
                              message: str,
                              delay: float,
                              store_command: bool = True):
    """Execute the spm start command with optional command storage"""
    user_id = ctx.author.id

    # Store command for auto-restart
    if store_command:
        store_last_command(prefix,
                           user_id,
                           'spm',
                           message=message,
                           delay=delay)

    # Create unique key for this bot and user combination
    spam_key = f"{prefix}_{user_id}"

    # Stop any existing spam for this user on this specific bot
    if spam_key in spam_tasks:
        spam_tasks[spam_key].cancel()
        spam_tasks.pop(spam_key, None)

    # Start the spam task - notify user via DM
    if store_command:  # Only notify on original command, not restarts
        try:
            await ctx.author.send(
                f"🚀 Starting spam on {prefix} bot: '{message}' with {delay}s delay. Use `{prefix}stop` or `{prefix}spm stop` to stop."
            )
        except:
            pass

    task = asyncio.create_task(
        spam_loop_with_restart(ctx, message, delay, prefix))
    spam_tasks[spam_key] = task

    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        spam_tasks.pop(spam_key, None)


def create_bot(prefix: str, bot_name: str):
    """Create a bot instance with the given prefix"""
    # Using discord.py-self - no intents or self_bot needed
    bot = commands.Bot(command_prefix=prefix)

    @bot.event
    async def on_ready():
        print(f"✅ {bot_name} logged in as {bot.user} (ID: {bot.user.id})")
        print(
            f"Bot is ready and listening for commands with prefix '{prefix}'")
        print(f"Authorized users: {ALLOWED_USERS}")

    @bot.check
    async def is_allowed(ctx):
        """Global check to ensure only authorized users can use bot commands"""
        is_authorized = ctx.author.id in ALLOWED_USERS
        # Debug: Print user ID for troubleshooting
        if not is_authorized:
            print(f"❌ Unauthorized user tried command: {ctx.author.id} (not in {ALLOWED_USERS})")
        else:
            print(f"✅ Authorized user {ctx.author.id} using command: {ctx.command}")
        return is_authorized

    @bot.command()
    async def send(ctx, message: str, delay: float, amount: int):
        """
        Send a message multiple times with a specified delay between each message.

        Usage: {prefix}send [message] [delay] [amount]
        Example: {prefix}send "Hello World" 1.0 5

        Parameters:
        - message: The message to send (use quotes for multi-word messages)
        - delay: Delay in seconds between messages (minimum 0.5 seconds)
        - amount: Number of times to send the message (1-20)
        """
        try:
            # Validate delay parameter
            if delay < MIN_DELAY:
                try:
                    await ctx.author.send(
                        f"⚠️ Delay must be at least {MIN_DELAY} seconds to prevent rate limiting."
                    )
                except:
                    pass
                return

            # Validate amount parameter
            if amount < 1 or amount > MAX_AMOUNT:
                try:
                    await ctx.author.send(
                        f"⚠️ Amount must be between 1 and {MAX_AMOUNT} messages."
                    )
                except:
                    pass
                return

            # Validate message length (Discord has a 2000 character limit)
            if len(message) > 2000:
                try:
                    await ctx.author.send(
                        "⚠️ Message is too long. Discord messages must be 2000 characters or less."
                    )
                except:
                    pass
                return

            # Delete the invoking command message to keep chat clean
            try:
                await ctx.message.delete()
            except discord.Forbidden:
                pass
            except Exception:
                pass

            await execute_send_command(ctx, message, delay, amount)

        except ValueError:
            try:
                await ctx.author.send(
                    f"⚠️ Invalid parameters. Please use: `{prefix}send [message] [delay] [amount]`\nExample: `{prefix}send \"Hello\" 1.0 5`"
                )
            except:
                pass
        except Exception as e:
            try:
                await ctx.author.send(f"⚠️ Error processing command: {e}")
            except:
                pass

    @bot.command()
    async def stop(ctx):
        """
        Stop any ongoing message sending for the user.

        Usage: {prefix}stop
        """
        user_id = ctx.author.id

        # Stop regular send command
        if user_id in stop_flags:
            stop_flags[user_id] = True
            try:
                await ctx.author.send("🛑 Stopping message sending...")
            except:
                pass

        # Stop spam command for this specific bot
        spam_key = f"{prefix}_{user_id}"
        if spam_key in spam_tasks:
            spam_tasks[spam_key].cancel()
            spam_tasks.pop(spam_key, None)
            try:
                await ctx.author.send(
                    f"🛑 Spam sending stopped on {prefix} bot.")
            except:
                pass

        # Clear last command to prevent auto-restart
        last_command_key = f"{prefix}_{user_id}"
        if last_command_key in last_commands:
            last_commands.pop(last_command_key, None)
            try:
                await ctx.author.send(
                    f"🛑 Auto-restart disabled for {prefix} bot.")
            except:
                pass

        if user_id not in stop_flags and spam_key not in spam_tasks:
            try:
                await ctx.author.send(
                    f"ℹ️ No active message sending to stop on {prefix} bot.")
            except:
                pass

    @bot.command()
    async def spm(ctx, action: str, message: str = None, delay: float = 1.0):
        """
        Continuous spam command with start/stop functionality.

        Usage: {prefix}spm start [message] [delay]
               {prefix}spm stop

        Examples:
        {prefix}spm start "Hello" 1.0
        {prefix}spm stop
        """
        user_id = ctx.author.id

        if action.lower() == "start":
            if not message:
                try:
                    await ctx.author.send(
                        f"⚠️ Please provide a message to spam.\nUsage: `{prefix}spm start \"message\" [delay]`"
                    )
                except:
                    pass
                return

            if delay < MIN_DELAY:
                try:
                    await ctx.author.send(
                        f"⚠️ Delay must be at least {MIN_DELAY} seconds.")
                except:
                    pass
                return

            # Delete the command message
            try:
                await ctx.message.delete()
            except Exception:
                pass

            await execute_spm_command(ctx, prefix, message, delay)

        elif action.lower() == "stop":
            spam_key = f"{prefix}_{user_id}"
            if spam_key in spam_tasks:
                spam_tasks[spam_key].cancel()
                spam_tasks.pop(spam_key, None)
                try:
                    await ctx.author.send(f"🛑 Spam stopped on {prefix} bot.")
                except:
                    pass

            # Clear last command to prevent auto-restart
            last_command_key = f"{prefix}_{user_id}"
            if last_command_key in last_commands:
                last_commands.pop(last_command_key, None)
                try:
                    await ctx.author.send(
                        f"🛑 Auto-restart disabled for {prefix} bot.")
                except:
                    pass

            if spam_key not in spam_tasks:
                try:
                    await ctx.author.send(
                        f"ℹ️ No active spam to stop on {prefix} bot.")
                except:
                    pass

        else:
            try:
                await ctx.author.send(
                    f"⚠️ Invalid action. Use `start` or `stop`.\nExample: `{prefix}spm start \"message\" 1.0`"
                )
            except:
                pass

    @bot.command()
    async def restart(ctx):
        """
        Manually restart the last command that was running on this bot.

        Usage: {prefix}restart
        """
        user_id = ctx.author.id
        key = f"{prefix}_{user_id}"

        if key not in last_commands:
            try:
                await ctx.author.send(
                    f"ℹ️ No previous command to restart on {prefix} bot.")
            except:
                pass
            return

        # Reset attempt counter for manual restart
        last_commands[key]['attempts'] = 0

        try:
            await ctx.author.send(
                f"🔄 Manually restarting last command on {prefix} bot...")
        except:
            pass

        await restart_last_command(ctx, prefix)

    @bot.command()
    async def help_bot(ctx):
        """Display help information about bot commands"""
        help_message = f"""🤖 **Discord Bot Help** (Prefix: {prefix})
Available commands for authorized users:

**`{prefix}send [message] [delay] [amount]`**
Send a message multiple times with delay
• message: Text to send (use quotes for spaces)
• delay: Seconds between messages (min {MIN_DELAY})
• amount: Number of repetitions (max {MAX_AMOUNT})
Example: `{prefix}send "Hello World" 1.0 3`

**`{prefix}spm start [message] [delay]`**
Start continuous spam (infinite messages until stopped)
• message: Text to spam (use quotes for spaces)
• delay: Seconds between messages (min {MIN_DELAY})
Example: `{prefix}spm start "Spam message" 0.5`

**`{prefix}spm stop`**
Stop continuous spam

**`{prefix}stop`**
Stop any active message sending (works for both send and spm)
Also disables auto-restart for this bot

**`{prefix}restart`**
Manually restart the last command that was running

**`>stopall`**
🚨 EMERGENCY STOP - Immediately stops ALL bots and commands
(Works with any bot, uses > prefix instead of {prefix})

**Auto-Restart Features**
• Commands automatically restart after errors (max {MAX_RESTART_ATTEMPTS} attempts)
• {RESTART_DELAY} second delay before restart attempts
• Manual restart available with `{prefix}restart`
• Auto-restart disabled when using stop commands

**Safety Features**
• Minimum delay: {MIN_DELAY} seconds
• User authorization required
• Individual stop controls per user
• Emergency stop for all bots
• Automatic command cleanup

Bot is running 24/7 on Replit with keep-alive monitoring"""

        await ctx.send(help_message)

    @bot.event
    async def on_message(message):
        """Handle emergency stopall command and regular commands"""
        global emergency_stop

        # Check for emergency stopall command
        if message.content == ">stopall" and message.author.id in ALLOWED_USERS:
            emergency_stop = True

            # Cancel all active spam tasks
            for spam_key, task in list(spam_tasks.items()):
                task.cancel()
                spam_tasks.pop(spam_key, None)

            # Set all stop flags
            for user_id in list(stop_flags.keys()):
                stop_flags[user_id] = True

            # Clear all last commands to prevent auto-restart
            last_commands.clear()

            try:
                await message.author.send(
                    "🚨 EMERGENCY STOP ACTIVATED - All bots stopped! Auto-restart disabled for all commands."
                )
            except:
                pass

            # Reset emergency stop after a brief moment to allow for new commands
            await asyncio.sleep(1)
            emergency_stop = False
            return

        # Check for account generation command
        if message.content.startswith(
                ">generate account") and message.author.id in ALLOWED_USERS:
            await handle_account_generation(message)
            return

        # Debug: Show when processing commands
        if message.content.startswith(('$', '!', '?', '>')) and message.author.id in ALLOWED_USERS:
            print(f"🔍 Processing command: '{message.content}' from user {message.author.id}")
        
        # Process normal commands
        await bot.process_commands(message)

    @bot.event
    async def on_command_error(ctx, error):
        """Handle command errors gracefully"""
        if isinstance(error, commands.CheckFailure):
            # Silently ignore authorization failures - no response to unauthorized users
            return
        elif isinstance(error, commands.CommandNotFound):
            # Only respond to command not found if user is authorized
            if ctx.author.id in ALLOWED_USERS:
                try:
                    await ctx.author.send(
                        f"⚠️ Unknown command. Use `{prefix}help_bot` for available commands."
                    )
                except:
                    pass
        elif isinstance(error, commands.MissingRequiredArgument):
            # Only respond to missing arguments if user is authorized
            if ctx.author.id in ALLOWED_USERS:
                try:
                    await ctx.author.send(
                        f"⚠️ Missing required arguments. Use `{prefix}help_bot` for command usage."
                    )
                except:
                    pass
        elif isinstance(error, commands.BadArgument):
            # Only respond to bad arguments if user is authorized
            if ctx.author.id in ALLOWED_USERS:
                try:
                    await ctx.author.send(
                        f"⚠️ Invalid argument type. Use `{prefix}help_bot` for command usage."
                    )
                except:
                    pass
        else:
            # Only respond to general errors if user is authorized
            if ctx.author.id in ALLOWED_USERS:
                try:
                    await ctx.author.send(f"⚠️ An error occurred: {error}")
                except:
                    pass
            print(f"Unhandled error in {bot_name}: {error}")

    return bot


async def handle_account_generation(message):
    """Handle account generation commands"""
    global generated_accounts, generation_tasks

    parts = message.content.split()
    if len(parts) < 3:
        try:
            await message.author.send(
                "⚠️ Usage: `>generate account [prefix]`\nExample: `>generate account &`"
            )
        except:
            pass
        return

    prefix = parts[2]
    user_id = message.author.id

    # Check if prefix is already in use
    if prefix in BOT_CONFIGS.values():
        try:
            await message.author.send(
                f"⚠️ Prefix '{prefix}' is already in use. Choose a different one."
            )
        except:
            pass
        return

    # Check if generation is already in progress for this user
    if user_id in generation_tasks:
        try:
            await message.author.send(
                "⚠️ Account generation already in progress. Please wait...")
        except:
            pass
        return

    try:
        await message.author.send(
            f"🔄 Starting account generation for prefix '{prefix}'...\nThis may take 5-10 minutes. You'll be notified when complete."
        )
    except:
        pass

    # Start generation task
    task = asyncio.create_task(generate_and_deploy_account(prefix, user_id))
    generation_tasks[user_id] = task


async def generate_and_deploy_account(prefix, user_id):
    """Generate account and deploy new bot"""
    global generated_accounts, generation_tasks, BOT_CONFIGS, bots

    try:
        # Generate account
        result = await account_generator.generate_account(use_temp_email=True,
                                                          use_sms=True)

        if result['success']:
            token = result['token']
            username = result['username']

            # Store account data
            generated_accounts[prefix] = result

            # Add to bot configs
            token_env_name = f"TOKEN_{prefix.upper()}"
            BOT_CONFIGS[token_env_name] = prefix

            # Set environment variable (temporary for this session)
            os.environ[token_env_name] = token

            # Create and start new bot
            bot_name = f"Bot-{prefix}"
            bot = create_bot(prefix, bot_name)
            bots[prefix] = bot

            # Start bot
            asyncio.create_task(bot.start(token))

            # Save to file for persistence
            await save_generated_accounts()

            # Notify user
            try:
                user = None
                for bot in bots.values():
                    try:
                        user = await bot.fetch_user(user_id)
                        break
                    except:
                        continue

                if user:
                    await user.send(
                        f"✅ Account generated successfully!\n"
                        f"**Prefix:** {prefix}\n"
                        f"**Username:** {username}\n"
                        f"**Bot Status:** Online and ready\n"
                        f"You can now use `{prefix}send`, `{prefix}spm`, etc.")
            except:
                pass
        else:
            # Notify failure
            try:
                user = None
                for bot in bots.values():
                    try:
                        user = await bot.fetch_user(user_id)
                        break
                    except:
                        continue

                if user:
                    await user.send(
                        f"❌ Account generation failed: {result.get('error', 'Unknown error')}"
                    )
            except:
                pass

    except Exception as e:
        try:
            user = None
            for bot in bots.values():
                try:
                    user = await bot.fetch_user(user_id)
                    break
                except:
                    continue

            if user:
                await user.send(f"❌ Account generation error: {str(e)}")
        except:
            pass

    finally:
        # Clean up task
        generation_tasks.pop(user_id, None)


async def save_generated_accounts():
    """Save generated accounts to file"""
    try:
        async with aiofiles.open('generated_accounts.json', 'w') as f:
            await f.write(json.dumps(generated_accounts, indent=2))
    except Exception as e:
        print(f"Failed to save accounts: {e}")


async def load_generated_accounts():
    """Load generated accounts from file"""
    global generated_accounts
    try:
        async with aiofiles.open('generated_accounts.json', 'r') as f:
            content = await f.read()
            generated_accounts = json.loads(content)

            # Restore BOT_CONFIGS
            for prefix, account_data in generated_accounts.items():
                token_env_name = f"TOKEN_{prefix.upper()}"
                BOT_CONFIGS[token_env_name] = prefix
                # Note: Tokens would need to be restored from secure storage

    except FileNotFoundError:
        generated_accounts = {}
    except Exception as e:
        print(f"Failed to load accounts: {e}")
        generated_accounts = {}


async def run_multiple_bots():
    """Run multiple bot instances simultaneously"""
    # Load existing generated accounts
    await load_generated_accounts()

    bot_tasks = []

    # Hardcoded tokens for local development
    HARDCODED_TOKENS = {
        "TOKEN":
        "",
        "TOKEN2":
        "",
        "TOKEN3": ""
    }

    for token_name, prefix in BOT_CONFIGS.items():
        # Use hardcoded token first, fallback to environment variable
        token = HARDCODED_TOKENS.get(token_name) or os.getenv(token_name)
        if token and token != f"YOUR_{token_name.split('TOKEN')[0]}DISCORD_TOKEN_HERE":
            bot = create_bot(prefix, f"Bot-{prefix}")
            bots[prefix] = bot  # Store by prefix for easier access

            # Create a task for this bot
            task = asyncio.create_task(bot.start(token))
            bot_tasks.append(task)
            print(f"🚀 Starting bot with prefix '{prefix}' using {token_name}")
        else:
            print(
                f"⚠️ {token_name} not found or using placeholder, skipping bot with prefix '{prefix}'"
            )

    if not bot_tasks:
        print(
            "❌ No valid tokens found. Please add at least TOKEN to your secrets."
        )
        return

    # Wait for all bots to finish (they should run indefinitely)
    try:
        await asyncio.gather(*bot_tasks)
    except Exception as e:
        print(f"❌ Error running bots: {e}")


if __name__ == "__main__":
    # Start the Flask keep-alive server
    keep_alive()

    print("🤖 Discord Multi-Bot System with Account Generation Starting...")
    print("=" * 70)

    # Check API keys for account generation
    # Hardcoded API keys for local development (optional)
    HARDCODED_API_KEYS = {
        "SMS_ACTIVATE_API_KEY": "",  # Add your SMS-Activate API key here
        "CAPTCHA_API_KEY": ""  # Add your CAPTCHA API key here  
    }

    sms_key = HARDCODED_API_KEYS.get("SMS_ACTIVATE_API_KEY") or os.getenv(
        'SMS_ACTIVATE_API_KEY')
    captcha_key = HARDCODED_API_KEYS.get("CAPTCHA_API_KEY") or os.getenv(
        'CAPTCHA_API_KEY')

    print("Account Generation Services:")
    print(
        f"  SMS Service: {'✅ Ready' if sms_key else '❌ Missing SMS_ACTIVATE_API_KEY'}"
    )
    print(
        f"  CAPTCHA Service: {'✅ Ready' if captcha_key else '❌ Missing CAPTCHA_API_KEY'}"
    )
    print()

    print("Configured bots:")
    for token_name, prefix in BOT_CONFIGS.items():
        token = os.getenv(token_name)
        status = "✅ Ready" if token else "❌ Missing"
        print(f"  {prefix} prefix - {token_name}: {status}")
    print()
    print("Commands:")
    print(
        "  >generate account [prefix] - Generate new Discord account and bot")
    print("  >stopall - Emergency stop all bots")
    print("=" * 70)

    try:
        asyncio.run(run_multiple_bots())
    except KeyboardInterrupt:
        print("\n🛑 Shutting down all bots...")
    except Exception as e:
        print(f"❌ Failed to start bots: {e}")
