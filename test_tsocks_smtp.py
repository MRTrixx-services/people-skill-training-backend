#!/usr/bin/env python3
import smtplib
import ssl
import os

# Force TSOCKS usage
os.environ['LD_PRELOAD'] = '/usr/lib/x86_64-linux-gnu/libtsocks.so'

print("Testing SMTP through TSOCKS...")

try:
    # SMTP settings
    smtp_server = "businessemail.webeyesoft.com"
    smtp_port = 465
    smtp_user = "support@peopleskilltraining.com"
    smtp_password = "^zD$Hvuv-WIt"
    
    print(f"Connecting to {smtp_server}:{smtp_port}...")
    
    # Create SSL context
    context = ssl.create_default_context()
    
    # Connect through TSOCKS
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        print("✅ Connected!")
        
        # Login
        server.login(smtp_user, smtp_password)
        print("✅ Login successful!")
        
        # Send test email
        sender = smtp_user
        receiver = "hariharasudhansara@gmail.com"
        message = f"""From: {sender}
To: {receiver}
Subject: Test via TSOCKS from VPS

This email was sent through TSOCKS tunnel from VPS!
"""
        server.sendmail(sender, receiver, message)
        print("✅ Email sent successfully through TSOCKS!")
        
except Exception as e:
    print(f"❌ Error: {e}")
