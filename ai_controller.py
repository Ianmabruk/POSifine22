"""
AI Controller
=============
API endpoints for AI-powered features:
- Sales forecasting
- Pro plan AI assistant
- Employee performance scoring
- Manual alert checks
"""

import asyncio
import logging
import json
from flask import Blueprint, request, jsonify, g
from functools import wraps
from typing import Dict, Any

from dto import ApiResponse
from middleware import error_handler, standardize_response
from ai_service import get_ai_service
from alert_engine import get_alert_engine

logger = logging.getLogger(__name__)


def require_admin(f):
    """Require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = g.get('user')
        if not user or user.get('role') not in ['admin', 'owner']:
            response = ApiResponse.error(
                message="Admin access required",
                errors=[{'field': 'auth', 'message': 'Insufficient permissions'}]
            )
            return jsonify(response.to_dict()), 403
        return f(*args, **kwargs)
    return decorated_function


def require_pro_plan(f):
    """Require Pro plan subscription"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = g.get('user')
        account = g.get('account')
        
        if not account or account.get('plan') not in ['pro', 'ultra']:
            response = ApiResponse.error(
                message="Pro plan required",
                errors=[{'field': 'subscription', 'message': 'Upgrade to Pro plan to access this feature'}]
            )
            return jsonify(response.to_dict()), 403
        return f(*args, **kwargs)
    return decorated_function


def create_ai_routes(datastore, auth_middleware):
    """
    Create AI feature routes
    
    Args:
        datastore: Database connection
        auth_middleware: Authentication middleware function
    """
    ai_bp = Blueprint('ai', __name__, url_prefix='/api/ai')
    
    ai_service = get_ai_service()
    
    # ============================================================
    # SALES FORECASTING
    # ============================================================
    
    @ai_bp.route('/forecast', methods=['GET'])
    @auth_middleware
    @require_admin
    @error_handler
    @standardize_response
    def forecast():
        """
        Get AI-powered sales forecast
        
        Returns:
            JSON with labels, revenue, and profit predictions
        """
        account_id = g.user.get('account_id')
        periods = int(request.args.get('periods', 4))
        
        try:
            # Get historical sales
            sales = datastore.get_by_field('sales', 'account_id', account_id)

            if not sales:
                return ApiResponse.success(data={
                    'labels': [f'Period {i+1}' for i in range(periods)],
                    'revenue': [0] * periods,
                    'profit': [0] * periods,
                    'note': 'No historical data available'
                }).to_dict(), 200

            def _run_async(coro):
                try:
                    loop = asyncio.get_running_loop()
                    if loop and loop.is_running():
                        new_loop = asyncio.new_event_loop()
                        try:
                            return new_loop.run_until_complete(coro)
                        finally:
                            new_loop.close()
                except RuntimeError:
                    pass
                return asyncio.run(coro)

            # Generate forecast with AI (safe across event loop contexts)
            forecast_data = _run_async(ai_service.forecast_sales(sales, periods=periods))

            return ApiResponse.success(
                data=forecast_data,
                message="Forecast generated successfully"
            ).to_dict(), 200

        except Exception as e:
            logger.exception("Forecast generation failed")
            return ApiResponse.success(data={
                'labels': [f'Period {i+1}' for i in range(periods)],
                'revenue': [0] * periods,
                'profit': [0] * periods,
                'note': f'Forecast unavailable: {str(e)}'
            }).to_dict(), 200
    
    # ============================================================
    # PRO PLAN AI ASSISTANT
    # ============================================================
    
    @ai_bp.route('/pro/ask', methods=['POST'])
    @auth_middleware
    @require_pro_plan
    @error_handler
    @standardize_response
    def pro_assistant():
        """
        AI assistant for Pro plan users
        
        Request body:
            {
                "question": "How can I improve bar sales?",
                "context": {}  // Optional business context
            }
        
        Returns:
            AI-generated advice specific to business type
        """
        user = g.user
        account = g.account
        data = request.get_json()
        
        question = data.get('question', '').strip()
        context = data.get('context')
        
        if not question:
            return ApiResponse.error(
                message="Question is required",
                errors=[{'field': 'question', 'message': 'Cannot be empty'}]
            ).to_dict(), 400
        
        try:
            # Get business type from account
            business_type = account.get('business_type', 'general')
            role = user.get('role', 'user')
            
            # Get AI response
            answer = asyncio.run(
                ai_service.business_assistant(
                    business_type=business_type,
                    role=role,
                    question=question,
                    context=context
                )
            )
            
            return ApiResponse.success(data={
                'answer': answer,
                'business_type': business_type,
                'timestamp': ApiResponse.success().timestamp
            }).to_dict(), 200
            
        except Exception as e:
            logger.exception("AI assistant failed")
            return ApiResponse.error(
                message=f"Assistant failed: {str(e)}"
            ).to_dict(), 500

    # ============================================================
    # ADMIN AI ASSISTANT
    # ============================================================

    @ai_bp.route('/ask', methods=['POST'])
    @auth_middleware
    @require_admin
    @error_handler
    @standardize_response
    def admin_assistant():
        """
        AI assistant for admin users

        Request body:
            {
                "question": "Draft an email to staff about schedule changes",
                "context": {}  // Optional business context
            }

        Returns:
            AI-generated response
        """
        user = g.user
        account = g.account
        data = request.get_json() or {}

        question = (data.get('question') or '').strip()
        context = data.get('context') or {}

        if not question:
            return ApiResponse.error(
                message="Question is required",
                errors=[{'field': 'question', 'message': 'Cannot be empty'}]
            ).to_dict(), 400

        def _run_async(coro):
            try:
                loop = asyncio.get_running_loop()
                if loop and loop.is_running():
                    new_loop = asyncio.new_event_loop()
                    try:
                        return new_loop.run_until_complete(coro)
                    finally:
                        new_loop.close()
            except RuntimeError:
                pass
            return asyncio.run(coro)

        try:
            business_type = (
                context.get('businessType')
                or (account.get('business_type') if account else None)
                or 'general'
            )
            role = user.get('role', 'admin')

            lower_q = question.lower()
            if ("forecast" in lower_q or "predict" in lower_q) and ("sale" in lower_q or "revenue" in lower_q):
                account_id = user.get('account_id')
                sales = datastore.get_by_field('sales', 'account_id', account_id)
                forecast = _run_async(ai_service.forecast_sales(sales, periods=4))

                lines = ["Sales forecast (next 4 periods):"]
                for i, label in enumerate(forecast.get('labels', [])):
                    revenue = forecast.get('revenue', [0] * 4)[i]
                    profit = forecast.get('profit', [0] * 4)[i]
                    lines.append(f"- {label}: revenue {revenue}, profit {profit}")

                return ApiResponse.success(data={
                    'answer': "\n".join(lines),
                    'business_type': business_type,
                    'timestamp': ApiResponse.success().timestamp
                }).to_dict(), 200

            prompt = f"""
You are a helpful AI business assistant for a {business_type}.
Respond clearly and concisely.
If the user asks to write an email, provide a subject line and a full email body.
If the user asks about sales forecasting, provide a brief forecast explanation.

User role: {role}
Question: {question}
Context: {json.dumps(context)}
"""

            answer = _run_async(ai_service.ask_ai(prompt, json_mode=False))

            return ApiResponse.success(data={
                'answer': answer,
                'business_type': business_type,
                'timestamp': ApiResponse.success().timestamp
            }).to_dict(), 200

        except Exception as e:
            logger.exception("Admin AI assistant failed")
            return ApiResponse.error(
                message=f"Assistant failed: {str(e)}"
            ).to_dict(), 500
    
    # ============================================================
    # EMPLOYEE PERFORMANCE SCORING
    # ============================================================
    
    @ai_bp.route('/staff-score', methods=['GET'])
    @auth_middleware
    @require_admin
    @error_handler
    @standardize_response
    def staff_scoring():
        """
        Get AI-powered employee performance scores
        
        Returns:
            List of employees with scores and reasons
        """
        account_id = g.user.get('account_id')
        
        try:
            # Get sales data with cashier info
            sales = datastore.get_by_field('sales', 'account_id', account_id)
            
            # Get time tracking data
            time_entries = datastore.get_by_field('time_tracking', 'account_id', account_id)
            
            if not sales and not time_entries:
                return ApiResponse.success(data={
                    'scores': [],
                    'note': 'No employee data available'
                }).to_dict(), 200
            
            # Generate scores with AI
            scores = asyncio.run(
                ai_service.score_staff_performance(sales, time_entries)
            )
            
            return ApiResponse.success(data={
                'scores': scores,
                'total_employees': len(scores),
                'timestamp': ApiResponse.success().timestamp
            }).to_dict(), 200
            
        except Exception as e:
            logger.exception("Staff scoring failed")
            return ApiResponse.error(
                message=f"Scoring failed: {str(e)}"
            ).to_dict(), 500
    
    # ============================================================
    # ALERT MANAGEMENT
    # ============================================================
    
    @ai_bp.route('/alerts/check', methods=['POST'])
    @auth_middleware
    @require_admin
    @error_handler
    @standardize_response
    def check_alerts():
        """
        Manually trigger alert check for current account
        
        Returns:
            List of detected alerts
        """
        account_id = g.user.get('account_id')
        
        try:
            alert_engine = get_alert_engine(datastore)
            if not alert_engine:
                return ApiResponse.error(
                    message="Alert engine not initialized"
                ).to_dict(), 500
            
            # Run check
            alerts = asyncio.run(
                alert_engine.check_account_now(account_id)
            )
            
            return ApiResponse.success(data={
                'alerts': alerts,
                'count': len(alerts),
                'timestamp': ApiResponse.success().timestamp
            }).to_dict(), 200
            
        except Exception as e:
            logger.exception("Alert check failed")
            return ApiResponse.error(
                message=f"Alert check failed: {str(e)}"
            ).to_dict(), 500
    
    @ai_bp.route('/alerts/config', methods=['GET', 'POST'])
    @auth_middleware
    @require_admin
    @error_handler
    @standardize_response
    def alert_config():
        """
        Get or update alert configuration
        
        GET: Returns current config
        POST: Updates config with provided values
        """
        alert_engine = get_alert_engine(datastore)
        if not alert_engine:
            return ApiResponse.error(
                message="Alert engine not initialized"
            ).to_dict(), 500
        
        if request.method == 'GET':
            # Return current config
            return ApiResponse.success(
                data=alert_engine.alert_config
            ).to_dict(), 200
        
        else:  # POST
            data = request.get_json()
            
            # Update config
            alert_engine.configure_alerts(
                revenue_threshold=data.get('revenue_drop_threshold'),
                expense_threshold=data.get('expense_spike_threshold'),
                channels=data.get('enabled_channels')
            )
            
            return ApiResponse.success(
                data=alert_engine.alert_config,
                message="Alert configuration updated"
            ).to_dict(), 200
    
    # ============================================================
    # AI SERVICE STATUS
    # ============================================================
    
    @ai_bp.route('/status', methods=['GET'])
    @auth_middleware
    @error_handler
    @standardize_response
    def ai_status():
        """
        Get AI service status and availability
        
        Returns:
            Service status information
        """
        return ApiResponse.success(data={
            'mode': ai_service.mode,
            'available': ai_service.mode in ['openai', 'fallback'],
            'features': {
                'forecasting': True,
                'assistant': True,
                'scoring': True,
                'alerts': get_alert_engine(datastore) is not None
            }
        }).to_dict(), 200
    
    return ai_bp
