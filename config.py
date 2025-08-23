# Configuration for Discord Account Generation System

# API Service Configuration
API_SERVICES = {
    'sms_activate': {
        'base_url': 'https://sms-activate.org/stubs/handler_api.php',
        'service_code': 'ds',  # Discord service code
        'country_code': '0'    # Any country
    },
    'captcha_2captcha': {
        'submit_url': 'http://2captcha.com/in.php',
        'result_url': 'http://2captcha.com/res.php'
    },
    'temp_email': {
        'base_url': 'https://www.1secmail.com/api/v1/'
    }
}

# Account Generation Settings
ACCOUNT_SETTINGS = {
    'username_length': (8, 12),
    'password_length': (12, 16),
    'max_generation_time': 600,  # 10 minutes
    'email_check_interval': 10,  # seconds
    'sms_check_interval': 10,    # seconds
    'captcha_timeout': 600       # 10 minutes
}

# Chrome Driver Settings
CHROME_OPTIONS = [
    "--headless",
    "--no-sandbox", 
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-web-security",
    "--disable-extensions",
    "--disable-plugins",
    "--disable-blink-features=AutomationControlled"
]

# Email Providers for Account Generation
EMAIL_PROVIDERS = [
    'gmail.com',
    'yahoo.com', 
    'outlook.com',
    'hotmail.com'
]

# User Agents for Stealth
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
]

# Success Messages
MESSAGES = {
    'generation_start': "🔄 Starting account generation for prefix '{}'...\nThis may take 5-10 minutes. You'll be notified when complete.",
    'generation_success': "✅ Account generated successfully!\n**Prefix:** {}\n**Username:** {}\n**Bot Status:** Online and ready\nYou can now use `{}send`, `{}spm`, etc.",
    'generation_failed': "❌ Account generation failed: {}",
    'prefix_in_use': "⚠️ Prefix '{}' is already in use. Choose a different one.",
    'generation_in_progress': "⚠️ Account generation already in progress. Please wait...",
    'invalid_usage': "⚠️ Usage: `>generate account [prefix]`\nExample: `>generate account &`"
}