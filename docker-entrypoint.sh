#!/bin/sh

set -e

echo ""
echo "==========================================="
echo "🚀 Starting PeopleSkillTraining Backend"
echo "==========================================="

echo ""
echo "⏳ Waiting for PostgreSQL..."

while ! nc -z db 5432; do
    sleep 2
done

echo "✅ PostgreSQL Connected."

echo ""
echo "⏳ Waiting for Redis..."

while ! nc -z redis 6379; do
    sleep 2
done

echo "✅ Redis Connected."

echo ""
echo "📦 Running Django Migrations..."
python manage.py migrate --noinput

echo ""
echo "📁 Collecting Static Files..."
python manage.py collectstatic --noinput

echo ""
echo "🔍 Checking Django Configuration..."
python manage.py check --deploy || true

echo ""
echo "==========================================="
echo "✅ Startup Completed"
echo "🚀 Launching Gunicorn..."
echo "==========================================="

exec "$@"