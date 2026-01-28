#!/usr/bin/env python3
"""
Quick Test Script for AI Features
Run this to verify your AI features are working correctly
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test if all required modules can be imported"""
    print("🧪 Testing Python imports...")
    
    try:
        import ai_service
        print("   ✅ ai_service.py")
    except Exception as e:
        print(f"   ❌ ai_service.py: {e}")
        return False
    
    try:
        import notify_service
        print("   ✅ notify_service.py")
    except Exception as e:
        print(f"   ❌ notify_service.py: {e}")
        return False
    
    try:
        import alert_engine
        print("   ✅ alert_engine.py")
    except Exception as e:
        print(f"   ❌ alert_engine.py: {e}")
        return False
    
    try:
        import ai_controller
        print("   ✅ ai_controller.py")
    except Exception as e:
        print(f"   ❌ ai_controller.py: {e}")
        return False
    
    return True

def test_ai_service():
    """Test AI service initialization"""
    print("\n🤖 Testing AI Service...")
    
    try:
        from ai_service import AIService
        ai = AIService()
        print(f"   ✅ AI Service initialized (mode: {ai.mode})")
        
        if ai.mode == 'openai':
            print("   ✅ OpenAI API key detected")
        else:
            print("   ⚠️  Using fallback mode (no OpenAI key)")
        
        return True
    except Exception as e:
        print(f"   ❌ AI Service failed: {e}")
        return False

def test_notification_service():
    """Test notification service"""
    print("\n📬 Testing Notification Service...")
    
    try:
        from notify_service import NotificationService
        notify = NotificationService()
        
        if notify.email_enabled:
            print("   ✅ Email configured")
        else:
            print("   ⚠️  Email not configured")
        
        if notify.whatsapp_enabled:
            print("   ✅ WhatsApp configured")
        else:
            print("   ⚠️  WhatsApp not configured")
        
        return True
    except Exception as e:
        print(f"   ❌ Notification Service failed: {e}")
        return False

def test_sample_forecast():
    """Test sample forecast generation"""
    print("\n📈 Testing Sample Forecast...")
    
    try:
        import asyncio
        from ai_service import get_ai_service
        
        ai = get_ai_service()
        
        # Sample sales data
        sample_sales = [
            {'total': 1000, 'gross_profit': 300, 'created_at': '2026-01-20T10:00:00'},
            {'total': 1200, 'gross_profit': 360, 'created_at': '2026-01-21T10:00:00'},
            {'total': 1100, 'gross_profit': 330, 'created_at': '2026-01-22T10:00:00'},
        ]
        
        forecast = asyncio.run(ai.forecast_sales(sample_sales, periods=4))
        
        print(f"   ✅ Forecast generated:")
        print(f"      Periods: {len(forecast['labels'])}")
        print(f"      Revenue forecast: {forecast['revenue']}")
        print(f"      Profit forecast: {forecast['profit']}")
        
        return True
    except Exception as e:
        print(f"   ❌ Forecast failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_environment():
    """Check environment variables"""
    print("\n🔐 Checking Environment Variables...")
    
    env_vars = {
        'OPENAI_API_KEY': 'OpenAI API',
        'EMAIL_USER': 'Email service',
        'EMAIL_PASS': 'Email password',
        'TWILIO_ACCOUNT_SID': 'Twilio SMS/WhatsApp',
        'DATABASE_URL': 'PostgreSQL database'
    }
    
    for var, name in env_vars.items():
        if os.environ.get(var):
            print(f"   ✅ {name} configured")
        else:
            print(f"   ⚠️  {name} not configured")

def main():
    """Run all tests"""
    print("=" * 60)
    print("🧪 AI FEATURES TEST SUITE")
    print("=" * 60)
    
    check_environment()
    
    if not test_imports():
        print("\n❌ Import test failed. Check your Python files.")
        return
    
    test_ai_service()
    test_notification_service()
    test_sample_forecast()
    
    print("\n" + "=" * 60)
    print("✅ ALL TESTS COMPLETE")
    print("=" * 60)
    print("\n💡 Next steps:")
    print("   1. Start your backend: cd backend && python app.py")
    print("   2. Test API: curl http://localhost:5000/api/ai/status")
    print("   3. Add components to your React dashboards")
    print("\n📚 See AI_FEATURES_COMPLETE.md for full documentation")

if __name__ == '__main__':
    main()
