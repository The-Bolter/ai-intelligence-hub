from gaming_attention import attention_level, enrich_event, score_event


def _event(event_type="major_update", **overrides):
    event = {
        "game_id": "GAME-1",
        "game_name": "示例游戏",
        "event_type": event_type,
        "event_name": "4.5版本更新",
        "start_date": "2026-08-28",
        "end_date": None,
        "key_changes": ["新角色"],
        "recommended_sources": [
            {"url": "https://game.example/news", "official": True, "priority": 100}
        ],
    }
    event.update(overrides)
    return event


def test_same_event_type_can_receive_different_scores():
    richer = _event(key_changes=["新地图", "新角色", "新活动"], game_scale="S")
    smaller = _event(key_changes=[], game_scale="C", recommended_sources=[])
    assert score_event(richer, "2026-08-28")[0] > score_event(smaller, "2026-08-28")[0]


def test_major_update_scores_above_weekly_update_all_else_equal():
    major = score_event(_event("major_update"), "2026-08-28")[0]
    weekly = score_event(_event("weekly_update"), "2026-08-28")[0]
    assert major > weekly


def test_beta_and_public_launch_have_high_milestone_value():
    beta = score_event(_event("test_or_launch", key_changes=["Beta测试"]), "2026-08-28")[1]
    public = score_event(_event("test_or_launch", key_changes=["公测"]), "2026-08-28")[1]
    assert beta["milestone_value"] >= 18
    assert public["milestone_value"] == 20


def test_content_count_and_official_priority_affect_factors():
    one = score_event(_event(key_changes=["新角色"]), "2026-08-28")[1]
    three = score_event(_event(key_changes=["新角色", "新地图", "新活动"]), "2026-08-28")[1]
    low = score_event(_event(recommended_sources=[{"url": "https://a", "official": True, "priority": 10}]), "2026-08-28")[1]
    high = score_event(_event(recommended_sources=[{"url": "https://a", "official": True, "priority": 100}]), "2026-08-28")[1]
    assert three["content_volume"] > one["content_volume"]
    assert high["official_strength"] > low["official_strength"]


def test_attention_level_boundaries():
    assert attention_level(75) == "高"
    assert attention_level(74) == "中高"
    assert attention_level(60) == "中高"
    assert attention_level(59) == "中"
    assert attention_level(40) == "中"
    assert attention_level(39) == "中低"


def test_enrichment_has_summary_impacts_and_factor_sum():
    enriched = enrich_event(_event(), "2026-08-28")
    assert enriched["summary"]
    assert enriched["impact_types"]
    assert enriched["hotspot_score"] == sum(enriched["score_factors"].values())
