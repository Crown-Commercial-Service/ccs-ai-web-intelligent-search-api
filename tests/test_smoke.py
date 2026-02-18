from dummy_flask_app2 import load_agreements


def test_load_agreements_smoke():
    agreements = load_agreements()
    assert isinstance(agreements, list)
    assert len(agreements) > 0

    first = agreements[0]
    # Basic schema expectations used by templates
    for key in (
        "title",
        "rm_number",
        "start_date",
        "end_date",
        "regulation",
        "summary",
        "description",
        "benefits",
        "how_to_buy",
        "lots",
        "lots_count",
    ):
        assert key in first

