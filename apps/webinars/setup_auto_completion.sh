#!/bin/bash
# Setup script for webinar auto-completion
# Ensures webinars are marked as completed after 24 hours

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(cd $SCRIPT_DIR/.. && pwd)"

echo "🔧 Setting up webinar auto-completion..."
echo ""

# Option 1: Via Middleware (automatic, no config needed)
echo "✅ Option 1: Automatic via Django Middleware"
echo "   Middleware is enabled in settings.py"
echo "   Runs every 30 minutes with each HTTP request"
echo "   No additional setup required!"
echo ""

# Option 2: Via Cron Job (guaranteed execution)
echo "📅 Option 2: Via Cron Job (RECOMMENDED)"
echo "   Add to crontab with: crontab -e"
echo ""
echo "   Copy and paste this line:"
echo ""
echo "   */30 * * * * cd $PROJECT_DIR && python manage.py force_complete_webinars --confirm >> /var/log/webinar-completion.log 2>&1"
echo ""
echo "   Or for every hour:"
echo "   0 * * * * cd $PROJECT_DIR && python manage.py force_complete_webinars --confirm >> /var/log/webinar-completion.log 2>&1"
echo ""

# Option 3: Via Celery Beat
echo "🚀 Option 3: Via Celery Beat (if running)"
echo "   Start Celery Beat with:"
echo "   celery -A peopleskilltrainingapp beat -l info"
echo ""
echo "   Or with worker:"
echo "   celery -A peopleskilltrainingapp worker -B -l info"
echo ""

# Option 4: Via systemd service
echo "🔧 Option 4: Via Systemd Service (production)"
echo "   Create /etc/systemd/system/webinar-completion.service:"
echo ""
cat << 'EOF'
[Unit]
Description=Webinar Auto-Completion Task
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/path/to/project
ExecStart=/usr/bin/python manage.py force_complete_webinars --confirm
Restart=always
RestartSec=300

[Install]
WantedBy=multi-user.target
EOF
echo ""

echo "================================"
echo "✅ Setup complete!"
echo "================================"
echo ""
echo "🎯 Recommended approach:"
echo "   1. Use Middleware (automatic) + Cron (guaranteed)"
echo "   2. Test with: python manage.py complete_scheduled_webinars --dry-run"
echo "   3. Run completion: python manage.py force_complete_webinars --confirm"
echo ""
