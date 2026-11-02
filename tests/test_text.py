"""Tests for the model-output text sanitizer."""

from __future__ import annotations

from naji.core.text import clean_spoken_text


def test_plain_text_is_unchanged() -> None:
    assert clean_spoken_text("  Olá, tudo bem?  ") == "Olá, tudo bem?"


def test_empty_text() -> None:
    assert clean_spoken_text("") == ""


def test_bold_and_italic_are_stripped() -> None:
    assert clean_spoken_text("O **clima** está *bom* hoje.") == "O clima está bom hoje."
    assert clean_spoken_text("__negrito__ e _itálico_") == "negrito e itálico"


def test_snake_case_is_preserved() -> None:
    assert clean_spoken_text("O valor de max_results é 5.") == "O valor de max_results é 5."


def test_code_fences_and_inline_code() -> None:
    text = "Use o comando:\n```bash\nnaji --smoke-test\n```\nOu digite `naji` no terminal."
    assert clean_spoken_text(text) == "Use o comando: naji --smoke-test Ou digite naji no terminal."


def test_links_keep_text_and_drop_url() -> None:
    text = "Veja [o site](https://exemplo.com) e a página https://outra.org/x."
    assert clean_spoken_text(text) == "Veja o site e a página"


def test_headings_lists_and_blockquote() -> None:
    text = "# Resultado\n- primeiro\n- segundo\n1. terceiro\n> citado"
    assert clean_spoken_text(text) == "Resultado primeiro segundo terceiro citado"


def test_table_becomes_comma_list() -> None:
    text = "| Dia | Tempo |\n| --- | --- |\n| Hoje | Sol |"
    assert clean_spoken_text(text) == "Dia, Tempo Hoje, Sol"


def test_html_tags_and_emojis_are_removed() -> None:
    text = "Pronto! <b>Feito</b> 🎉✅"
    assert clean_spoken_text(text) == "Pronto! Feito"


def test_multiline_answer_collapses_to_one_line() -> None:
    text = "Resposta:\n\n**Resumo**\n- item A\n- item B"
    assert clean_spoken_text(text) == "Resposta: Resumo item A item B"
