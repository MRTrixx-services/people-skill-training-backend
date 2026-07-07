import smtplib
from email.mime.text import MIMEText

def test_smtp():
    """Test SMTP connection"""
    configs = [
        ('businessemail.webeyesoft.com', 465, True, False),  # SSL
        ('businessemail.webeyesoft.com', 587, False, True),  # TLS
        ('smtp.gmail.com', 587, False, True),  # Gmail
    ]
    
    for host, port, use_ssl, use_tls in configs:
        print(f"\n🔍 Testing {host}:{port} (SSL={use_ssl}, TLS={use_tls})")
        
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, timeout=10)
            else:
                server = smtplib.SMTP(host, port, timeout=10)
                if use_tls:
                    server.starttls()
            
            # Try to login
            server.login('support@peopleskilltraining.com', 'YOUR_PASSWORD')
            print(f"✅ SUCCESS: {host}:{port}")
            server.quit()
            return True
            
        except Exception as e:
            print(f"❌ FAILED: {str(e)}")
    
    return False

if __name__ == '__main__':
    test_smtp()
