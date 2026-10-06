"""The brand prompt tells the model that the charter's own tagline is not an exclusion violation."""

from airlock.gates.brand import load_charter, prompt_for


def test_the_prompt_clears_the_charters_own_tagline():
    charter = load_charter()
    prompt = prompt_for(charter)
    assert f'The tagline "{charter["tagline"]}" and the wordmark are the brand\'s own approved wording' in prompt
    assert "every charter exclusion that the asset violates" in prompt


def test_a_charter_without_a_tagline_gets_no_such_sentence():
    charter = {k: v for k, v in load_charter().items() if k != "tagline"}
    assert "approved wording" not in prompt_for(charter)
