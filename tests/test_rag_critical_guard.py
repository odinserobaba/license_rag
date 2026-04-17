import app


def _mk_match(
    text: str,
    doc_type: str = "ФЕДЕРАЛЬНЫЙ ЗАКОН",
    doc_number: str = "171-ФЗ",
    source_file: str = "fz-22_11_1995.rtf",
):
    return (
        1.0,
        {
            "text": text,
            "metadata": {
                "doc_type": doc_type,
                "doc_number_text": doc_number,
                "source_file": source_file,
            },
        },
    )


def test_retail_query_detection_true():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    assert app.is_retail_license_authority_query(q) is True


def test_retail_query_detection_false():
    q = "Какие документы нужны для продления лицензии на производство?"
    assert app.is_retail_license_authority_query(q) is False


def test_guard_corrects_forbidden_federal_claim():
    question = "Кто выдает лицензию на розничную продажу алкоголя?"
    bad_answer = (
        "Лицензию на розничную продажу алкогольной продукции выдает "
        "Росалкогольрегулирование."
    )
    matches = [_mk_match("... статья 19 171-ФЗ ...")]
    fixed, notes = app.enforce_critical_fact_guard(question, bad_answer, matches)
    assert "субъекта Российской Федерации" in fixed
    assert "retail_authority_corrected" in notes
    assert "retail_authority_forbidden_claim_detected" in notes


def test_guard_keeps_correct_answer():
    question = "Кто выдает лицензию на розничную продажу алкоголя?"
    good_answer = (
        "Лицензия на розничную продажу алкогольной продукции выдается "
        "уполномоченным органом исполнительной власти субъекта Российской Федерации."
    )
    matches = [_mk_match("... статья 19 171-ФЗ ...")]
    fixed, notes = app.enforce_critical_fact_guard(question, good_answer, matches)
    assert fixed == good_answer
    assert notes == []


def test_sanitize_hallucinated_doc_mentions_removes_unknown_bullets():
    text = (
        "### Источники\n"
        "- Постановление №723 от 17.07.2012\n"
        "- Федеральный закон №171-ФЗ\n"
        "В тексте встречается №374-ФЗ."
    )
    cleaned, removed = app.sanitize_hallucinated_doc_mentions(text, ["723", "374-фз"])
    assert removed >= 1
    assert "№723" not in cleaned
    assert "№171-ФЗ" in cleaned
    assert "реквизит требует проверки" in cleaned


def test_build_prompts_include_retail_jurisdiction_rule():
    matches = [_mk_match("... статья 16 и 19 171-ФЗ ...")]
    legal_prompt = app.build_legal_prompt("Кто выдает розничную лицензию?", matches)
    concise_prompt = app.build_concise_prompt("Кто выдает розничную лицензию?", matches, [])
    assert "уполномоченным органом субъекта Российской Федерации" in legal_prompt
    assert "орган выдачи лицензии — уполномоченный орган субъекта РФ" in concise_prompt


def test_sanitize_does_not_corrupt_171_when_single_digit_hallucination_present():
    text = "См. [Федеральный закон № 171-ФЗ](http://www.kremlin.ru/acts/bank/8506)."
    cleaned, removed = app.sanitize_hallucinated_doc_mentions(text, ["1"])
    assert removed == 0
    assert "№ 171-ФЗ" in cleaned
    assert "НПА вне текущего контекста71-ФЗ" not in cleaned
    assert "НПА вне текущего контекста" not in cleaned


def test_find_doc_numbers_ignores_single_digit_markers():
    used = app.find_doc_numbers_in_text("Пункт №1 и закон №171-ФЗ.")
    assert "1" not in used
    assert "171" in used
    assert "171-фз" in used


def test_sanitize_keeps_markdown_link_line_unchanged():
    line = "- [Федеральный закон № 171-ФЗ](http://www.kremlin.ru/acts/bank/8506)"
    cleaned, removed = app.sanitize_hallucinated_doc_mentions(line, ["171"])
    assert removed == 1
    assert cleaned == ""


def test_sanitize_uses_harmless_placeholder():
    text = "В тексте упомянут №723, которого нет в контексте."
    cleaned, _ = app.sanitize_hallucinated_doc_mentions(text, ["723"])
    assert "реквизит требует проверки" in cleaned
    assert "НПА вне текущего контекста" not in cleaned


def test_sanitize_unverified_doc_refs_keeps_allowed_and_replaces_unknown():
    matches = [_mk_match("...", doc_number="171-ФЗ")]
    text = "См. №171-ФЗ и №723."
    cleaned, replaced = app.sanitize_unverified_doc_refs(text, matches)
    assert "№171-ФЗ" in cleaned
    assert "№ [проверить реквизит]" in cleaned
    assert replaced >= 1


def test_enforce_strict_sources_rebuilds_from_matches():
    matches = [_mk_match("...", doc_number="171-ФЗ")]
    text = "### Краткий ответ\nТест.\n\n### Источники\n- Левый источник\n\n### Официальные ссылки\n- x"
    rebuilt, removed = app.enforce_strict_sources(text, matches, limit=4)
    assert removed is True
    assert "- Левый источник" not in rebuilt
    assert "### Источники" in rebuilt
    assert "171-ФЗ" in rebuilt
