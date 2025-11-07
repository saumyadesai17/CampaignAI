"""
Email Configuration Test Script
Run this script to verify your email configuration before deploying to Render

Usage:
    python test_email_config.py
"""

import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()

def test_environment_variables():
    """Test if all required environment variables are set"""
    print("=" * 60)
    print("1️⃣  TESTING ENVIRONMENT VARIABLES")
    print("=" * 60)
    
    required_vars = {
        "SENDER_EMAIL": os.getenv("SENDER_EMAIL"),
        "SENDER_PASSWORD": os.getenv("SENDER_PASSWORD"),
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY")
    }
    
    optional_vars = {
        "SENDER_NAME": os.getenv("SENDER_NAME", "Not set (will use company name)")
    }
    
    all_set = True
    
    for var_name, var_value in required_vars.items():
        if var_value:
            print(f"✅ {var_name}: Set ({var_value[:10]}...)")
        else:
            print(f"❌ {var_name}: NOT SET")
            all_set = False
    
    for var_name, var_value in optional_vars.items():
        print(f"ℹ️  {var_name}: {var_value}")
    
    print()
    
    if not all_set:
        print("❌ FAILED: Some required environment variables are missing!")
        print("\nCreate a .env file with:")
        print("SENDER_EMAIL=your-email@gmail.com")
        print("SENDER_PASSWORD=your-app-password")
        print("GROQ_API_KEY=your-groq-key")
        return False
    
    print("✅ All required environment variables are set!")
    return True

def test_groq_api():
    """Test if Groq API is working"""
    print("\n" + "=" * 60)
    print("2️⃣  TESTING GROQ API")
    print("=" * 60)
    
    try:
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        print("✅ Groq client initialized successfully")
        
        # Test API call
        print("📝 Testing content generation...")
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Say 'Email test successful!' in 5 words"}]
        )
        
        content = response.choices[0].message.content.strip()
        print(f"✅ Groq API working! Response: {content}")
        return True
        
    except Exception as e:
        print(f"❌ Groq API error: {str(e)}")
        print("\nCheck your GROQ_API_KEY:")
        print("1. Go to https://console.groq.com/keys")
        print("2. Create a new API key")
        print("3. Set it in your .env file")
        return False

def test_smtp_connection():
    """Test SMTP connection to Gmail"""
    print("\n" + "=" * 60)
    print("3️⃣  TESTING GMAIL SMTP CONNECTION")
    print("=" * 60)
    
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    
    try:
        print("📬 Connecting to smtp.gmail.com:587...")
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        print("✅ Connected to SMTP server")
        
        print("🔐 Starting TLS encryption...")
        server.starttls()
        print("✅ TLS encryption started")
        
        print(f"🔑 Logging in as {sender_email}...")
        server.login(sender_email, sender_password)
        print("✅ SMTP login successful!")
        
        server.quit()
        print("✅ SMTP connection test passed!")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"❌ SMTP Authentication failed: {str(e)}")
        print("\n⚠️  You need a Gmail App Password, not your regular password!")
        print("\nHow to create a Gmail App Password:")
        print("1. Go to https://myaccount.google.com/apppasswords")
        print("2. Enable 2-Step Verification if not already enabled")
        print("3. Create a new App Password for 'Mail'")
        print("4. Copy the 16-character password")
        print("5. Use it as SENDER_PASSWORD in your .env file")
        return False
        
    except Exception as e:
        print(f"❌ SMTP connection error: {str(e)}")
        print("\nPossible issues:")
        print("- Network/firewall blocking port 587")
        print("- Invalid email address")
        print("- Gmail security settings")
        return False

def test_send_email():
    """Test sending an actual email"""
    print("\n" + "=" * 60)
    print("4️⃣  TESTING EMAIL SENDING")
    print("=" * 60)
    
    sender_email = os.getenv("SENDER_EMAIL")
    sender_password = os.getenv("SENDER_PASSWORD")
    sender_name = os.getenv("SENDER_NAME", "CampaignAI Test")
    
    # Send to the same email for testing
    test_recipient = sender_email
    
    try:
        print(f"📧 Sending test email to {test_recipient}...")
        
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            
            # Create test email
            msg = MIMEText(
                "This is a test email from CampaignAI.\n\n"
                "If you're seeing this, your email configuration is working correctly!\n\n"
                "You're ready to deploy to Render.",
                "plain"
            )
            msg["Subject"] = "CampaignAI Email Configuration Test"
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = test_recipient
            
            server.send_message(msg)
            
        print(f"✅ Test email sent successfully to {test_recipient}")
        print(f"📬 Check your inbox at {test_recipient}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send email: {str(e)}")
        return False

def main():
    """Run all tests"""
    print("\n" + "🧪 " * 20)
    print("CAMPAIGNAI EMAIL CONFIGURATION TEST")
    print("🧪 " * 20 + "\n")
    
    results = {
        "Environment Variables": test_environment_variables(),
        "Groq API": False,
        "SMTP Connection": False,
        "Send Email": False
    }
    
    # Only test Groq if env vars are set
    if results["Environment Variables"]:
        results["Groq API"] = test_groq_api()
        results["SMTP Connection"] = test_smtp_connection()
        
        # Only test sending if SMTP connection works
        if results["SMTP Connection"]:
            results["Send Email"] = test_send_email()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {test_name}")
    
    print()
    
    if all(results.values()):
        print("🎉 " * 10)
        print("ALL TESTS PASSED!")
        print("🎉 " * 10)
        print("\n✅ Your email configuration is ready for Render deployment!")
        print("\nNext steps:")
        print("1. Set the same environment variables on Render:")
        print(f"   - SENDER_EMAIL={os.getenv('SENDER_EMAIL')}")
        print(f"   - SENDER_PASSWORD=[your app password]")
        print(f"   - GROQ_API_KEY=[your groq key]")
        print("2. Deploy your application")
        print("3. Test the /email_campaign endpoint")
    else:
        print("❌ " * 10)
        print("SOME TESTS FAILED")
        print("❌ " * 10)
        print("\n⚠️  Fix the failed tests before deploying to Render.")
        print("See the error messages above for specific fixes.")

if __name__ == "__main__":
    main()
