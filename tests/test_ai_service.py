from ai_service import AIService


def test_posifne_default_schema():
    service = AIService(api_key=None)
    insights = service._default_posifne_insights()
    assert "forecast" in insights
    assert "anomalies" in insights
    assert "inventory" in insights
    assert "promotions" in insights
    assert "strategy" in insights


def test_posifne_validation_normalizes():
    service = AIService(api_key=None)
    payload = {
        "forecast": {"next_7_days": 123},
        "anomalies": [{"type": "theft", "description": "odd", "risk_level": "extreme"}],
        "inventory": {"hot_items": ["A"], "dead_stock": ["B"], "reorder_suggestions": ["C"]},
        "promotions": [{"bundle": "A+B", "reason": "boost"}],
        "strategy": {"staffing": "more", "pricing": "adjust", "operations": "tighten"}
    }
    normalized = service._validate_posifne_insights(payload)
    assert normalized["forecast"]["next_7_days"] == "123"
    assert normalized["anomalies"][0]["risk_level"] == "low"
