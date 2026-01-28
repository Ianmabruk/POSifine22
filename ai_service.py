"""
AI Service Layer
=================
OpenAI/Claude integration for intelligent POS features:
- Sales forecasting
- Anomaly detection
- Business insights
- Employee performance analysis
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Try OpenAI first, fallback to basic AI
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    logger.warning("OpenAI not installed. AI features will use fallback mode.")


class AIService:
    """
    AI Service for intelligent POS analysis
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize AI service"""
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY')
        
        if HAS_OPENAI and self.api_key:
            # Use new OpenAI client (v1.0+)
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
            self.mode = 'openai'
            logger.info("AI Service initialized with OpenAI")
        else:
            self.client = None
            self.mode = 'fallback'
            logger.info("AI Service initialized in fallback mode")
    
    async def ask_ai(self, prompt: str, json_mode: bool = True) -> str:
        """
        Send prompt to AI and get response
        
        Args:
            prompt: The prompt to send
            json_mode: Whether to expect JSON response
            
        Returns:
            AI response as string
        """
        try:
            if self.mode == 'openai':
                return await self._ask_openai(prompt, json_mode)
            else:
                return self._fallback_response(prompt)
        except Exception as e:
            logger.error(f"AI request failed: {e}")
            return self._fallback_response(prompt)
    
    async def _ask_openai(self, prompt: str, json_mode: bool) -> str:
        """Send request to OpenAI API"""
        try:
            # Use new OpenAI client API (v1.0+)
            # Using gpt-4o-mini for cost-effectiveness
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are an expert POS system analyst."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return self._fallback_response(prompt)
    
    def _fallback_response(self, prompt: str) -> str:
        """Simple fallback when OpenAI unavailable"""
        if "forecast" in prompt.lower():
            return json.dumps({
                "labels": ["Week 1", "Week 2", "Week 3", "Week 4"],
                "revenue": [10000, 12000, 11500, 13000],
                "profit": [3000, 3600, 3450, 3900]
            })
        elif "score" in prompt.lower() or "staff" in prompt.lower():
            return json.dumps([
                {"name": "Employee 1", "score": 85, "reason": "Strong sales performance"},
                {"name": "Employee 2", "score": 92, "reason": "Excellent consistency"}
            ])
        elif "alert" in prompt.lower():
            return json.dumps({
                "alerts": [],
                "message": "No anomalies detected"
            })
        else:
            return "AI service temporarily unavailable. Please check configuration."
    
    # ============================================================
    # SALES FORECASTING
    # ============================================================
    
    async def forecast_sales(
        self,
        sales_data: List[Dict],
        periods: int = 4
    ) -> Dict[str, List]:
        """
        Forecast future sales based on historical data
        
        Args:
            sales_data: Historical sales records
            periods: Number of periods to forecast
            
        Returns:
            Dict with labels, revenue, and profit predictions
        """
        # Aggregate sales by week/month
        aggregated = self._aggregate_sales(sales_data)
        
        prompt = f"""
Analyze sales data and forecast next {periods} periods.
Return ONLY valid JSON in this exact format:
{{
  "labels": ["Period 1", "Period 2", ...],
  "revenue": [amount1, amount2, ...],
  "profit": [profit1, profit2, ...]
}}

Historical Data:
{json.dumps(aggregated, indent=2)}

Consider:
- Trends and seasonality
- Growth patterns
- Recent performance
"""
        
        response = await self.ask_ai(prompt, json_mode=True)
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return self._default_forecast(periods)
    
    def _aggregate_sales(self, sales_data: List[Dict]) -> List[Dict]:
        """Aggregate sales data by week"""
        from collections import defaultdict
        
        weekly = defaultdict(lambda: {'revenue': 0, 'profit': 0, 'count': 0})
        
        for sale in sales_data[:100]:  # Last 100 sales
            try:
                created_at = datetime.fromisoformat(sale.get('created_at', ''))
                week = created_at.strftime('%Y-W%U')
                
                weekly[week]['revenue'] += sale.get('total', 0)
                weekly[week]['profit'] += sale.get('gross_profit', 0)
                weekly[week]['count'] += 1
            except:
                continue
        
        return [
            {
                'period': week,
                'revenue': data['revenue'],
                'profit': data['profit'],
                'sales_count': data['count']
            }
            for week, data in sorted(weekly.items())[-12:]  # Last 12 weeks
        ]
    
    def _default_forecast(self, periods: int) -> Dict[str, List]:
        """Default forecast when AI unavailable"""
        return {
            "labels": [f"Period {i+1}" for i in range(periods)],
            "revenue": [10000 * (1 + i * 0.1) for i in range(periods)],
            "profit": [3000 * (1 + i * 0.1) for i in range(periods)]
        }
    
    # ============================================================
    # ANOMALY DETECTION
    # ============================================================
    
    async def detect_anomalies(
        self,
        sales_data: List[Dict],
        expenses_data: List[Dict],
        threshold: float = 0.3
    ) -> List[Dict]:
        """
        Detect unusual patterns in business data
        
        Args:
            sales_data: Recent sales records
            expenses_data: Recent expense records
            threshold: Sensitivity (0-1)
            
        Returns:
            List of detected anomalies
        """
        # Calculate metrics
        metrics = self._calculate_metrics(sales_data, expenses_data)
        
        prompt = f"""
Analyze POS data for anomalies and concerns.
Return ONLY valid JSON array:
[
  {{"type": "revenue_drop", "severity": "high", "message": "...", "action": "..."}},
  ...
]

Current Metrics:
{json.dumps(metrics, indent=2)}

Severity levels: critical, high, medium, low
Types: revenue_drop, expense_spike, low_sales, inventory_issue, staff_performance
"""
        
        response = await self.ask_ai(prompt, json_mode=True)
        
        try:
            anomalies = json.loads(response)
            return anomalies if isinstance(anomalies, list) else []
        except:
            return []
    
    def _calculate_metrics(self, sales: List[Dict], expenses: List[Dict]) -> Dict:
        """Calculate key business metrics"""
        now = datetime.now()
        today_sales = [s for s in sales if datetime.fromisoformat(s.get('created_at', '')).date() == now.date()]
        week_sales = [s for s in sales if datetime.fromisoformat(s.get('created_at', '')) > now - timedelta(days=7)]
        
        return {
            'today_revenue': sum(s.get('total', 0) for s in today_sales),
            'today_sales_count': len(today_sales),
            'week_revenue': sum(s.get('total', 0) for s in week_sales),
            'week_sales_count': len(week_sales),
            'week_expenses': sum(e.get('amount', 0) for e in expenses[-7:]),
            'avg_sale_value': sum(s.get('total', 0) for s in week_sales) / max(len(week_sales), 1)
        }
    
    # ============================================================
    # EMPLOYEE PERFORMANCE
    # ============================================================
    
    async def score_staff_performance(
        self,
        sales_data: List[Dict],
        time_tracking: List[Dict]
    ) -> List[Dict]:
        """
        Score employee performance based on sales and hours
        
        Args:
            sales_data: Sales records with cashier info
            time_tracking: Time tracking records
            
        Returns:
            List of employee scores
        """
        # Aggregate by employee
        staff_metrics = self._aggregate_staff_metrics(sales_data, time_tracking)
        
        prompt = f"""
Score staff performance (1-100) based on metrics.
Return ONLY valid JSON array:
[
  {{"name": "Employee Name", "score": 85, "reason": "Brief explanation"}},
  ...
]

Staff Metrics:
{json.dumps(staff_metrics, indent=2)}

Consider:
- Sales volume and value
- Hours worked vs productivity
- Consistency
- Customer service (if available)
"""
        
        response = await self.ask_ai(prompt, json_mode=True)
        
        try:
            scores = json.loads(response)
            return scores if isinstance(scores, list) else []
        except:
            return self._default_staff_scores(staff_metrics)
    
    def _aggregate_staff_metrics(
        self,
        sales: List[Dict],
        time_entries: List[Dict]
    ) -> List[Dict]:
        """Aggregate metrics by staff member"""
        from collections import defaultdict
        
        staff = defaultdict(lambda: {
            'sales_count': 0,
            'total_revenue': 0,
            'total_profit': 0,
            'hours_worked': 0
        })
        
        # Aggregate sales
        for sale in sales:
            cashier_name = sale.get('cashier_name', 'Unknown')
            staff[cashier_name]['sales_count'] += 1
            staff[cashier_name]['total_revenue'] += sale.get('total', 0)
            staff[cashier_name]['total_profit'] += sale.get('gross_profit', 0)
        
        # Aggregate hours
        for entry in time_entries:
            name = entry.get('cashier_name', 'Unknown')
            duration = entry.get('duration_minutes', 0)
            staff[name]['hours_worked'] += duration / 60
        
        return [
            {
                'name': name,
                **metrics,
                'revenue_per_hour': metrics['total_revenue'] / max(metrics['hours_worked'], 1)
            }
            for name, metrics in staff.items()
        ]
    
    def _default_staff_scores(self, staff_metrics: List[Dict]) -> List[Dict]:
        """Default scoring when AI unavailable"""
        return [
            {
                'name': metric['name'],
                'score': min(100, int(metric['revenue_per_hour'] / 100)),
                'reason': f"${metric['total_revenue']:.0f} revenue, {metric['hours_worked']:.1f}h worked"
            }
            for metric in staff_metrics[:10]
        ]
    
    # ============================================================
    # BUSINESS ASSISTANT
    # ============================================================
    
    async def business_assistant(
        self,
        business_type: str,
        role: str,
        question: str,
        context: Optional[Dict] = None
    ) -> str:
        """
        AI assistant for specific business types
        
        Args:
            business_type: clinic, bar, hotel, etc.
            role: admin, cashier, owner
            question: User's question
            context: Optional business context
            
        Returns:
            AI response
        """
        prompt = f"""
You are an expert {business_type} management assistant.
User role: {role}

Question: {question}

{f"Context: {json.dumps(context)}" if context else ""}

Provide practical, actionable advice specific to {business_type} operations.
"""
        
        response = await self.ask_ai(prompt, json_mode=False)
        return response


# Global AI service instance
_ai_service = None


def get_ai_service() -> AIService:
    """Get or create AI service singleton"""
    global _ai_service
    if _ai_service is None:
        _ai_service = AIService()
    return _ai_service
