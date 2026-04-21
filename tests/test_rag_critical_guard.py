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


def test_applicant_clarification_retail_avoids_transport_checklist():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    bullets = app.applicant_clarification_bullets(q)
    joined = " ".join(bullets).lower()
    assert "дал/год" not in joined
    assert "нефасованная спиртосодержащая" not in joined


def test_applicant_clarification_transport_keeps_ethanol_context():
    q = "Какие документы нужны для лицензии на перевозки этилового спирта?"
    bullets = app.applicant_clarification_bullets(q)
    joined = " ".join(bullets).lower()
    assert "этилов" in joined or "спирт" in joined
    assert "перевоз" in joined or "дал" in joined


def test_llm_unavailability_bannermentions_fallback():
    b = app.llm_availability_user_banner("[LLM недоступна] Error code: 503")
    assert "Сервис генерации временно недоступен" in b
    assert "локального контекста" in b


def test_build_requisites_review_block_when_unverified_present():
    block = app.build_requisites_review_block(2)
    assert "Контроль реквизитов" in block
    assert "проверить реквизит" in block


def test_dedupe_sources_sections_merges_same_law_variants():
    text = (
        "### Краткий ответ\nok\n\n"
        "### Источники\n"
        "- Федеральный закон № 171-ФЗ\n"
        "- 171-фз\n"
        "- [Федеральный закон №171-ФЗ](http://example.com)\n"
    )
    out = app.dedupe_sources_sections(text)
    assert out.count("### Источники") == 1
    # Only one bullet for the 171-FZ family should remain.
    assert out.count("\n- ") == 1


def test_sanitize_clarification_removes_transport_bullets_for_non_transport_question():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    text = (
        "### Краткий ответ\nok\n\n"
        "### Что нужно уточнить у заявителя\n"
        "- Тип продукции: этиловый спирт или нефасованная спиртосодержащая продукция (>25%).\n"
        "- Планируемый годовой объем перевозок (в дал/год).\n"
        "- Субъект РФ и адрес объекта.\n"
    )
    out = app.sanitize_clarification_block_by_topic(text, q)
    assert "дал/год" not in out.lower()
    assert "нефасованная спиртосодержащая" not in out.lower()
    assert "Субъект РФ и адрес объекта." in out


def test_license_term_guard_injects_five_years_fact_when_missing():
    q = "На какой срок может быть выдана или продлена лицензия?"
    text = "Срок действия лицензии в предоставленных источниках не уточняется."
    fixed, notes = app.enforce_license_term_guard(q, text, [_mk_match("... статья 18 171-ФЗ ...")])
    assert ("пяти лет" in fixed.lower()) or ("5 лет" in fixed.lower())
    assert "license_term_corrected" in notes


def test_user_mode_sanitizer_drops_critical_fact_header():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    text = (
        "### Критическая проверка фактов\n"
        "Служебный блок.\n\n"
        "### Краткий ответ\n"
        "Лицензию выдает субъект РФ.\n\n"
        "### Источники\n- x"
    )
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "Критическая проверка фактов" not in out


def test_user_mode_retail_force_direct_competence_fact():
    q = "Кто выдает лицензию на розничную продажу алкоголя?"
    text = "### Краткий ответ\nНужно уточнить в источниках."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "уполномоч" in low and "субъект" in low


def test_user_mode_fee_question_adds_33333_anchor():
    q = "Какой порядок уплаты госпошлины при лицензировании?"
    text = "### Краткий ответ\nОплатите госпошлину."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "333.33" in out


def test_user_mode_field_assessment_exceptions_adds_point_29():
    q = "В каких случаях выездная оценка может не проводиться?"
    text = "### Краткий ответ\nНужно проверить правила."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "пункте 29" in out or "пункт 29" in out


def test_user_mode_statement_details_adds_article_19_anchor():
    q = "Какие сведения должны быть в заявлении о выдаче лицензии?"
    text = "### Краткий ответ\nУкажите сведения о заявителе."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "заявлен" in low
    assert "статье 19" in low or "статья 19" in low


def test_user_mode_fixation_question_adds_order_397_anchor():
    q = "Какие требования к специальным техническим средствам фиксации движения?"
    text = "### Краткий ответ\nТребования устанавливаются профильным приказом."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert ("№ 397" in out) or ("№397" in out)


def test_user_mode_submission_channel_adds_unified_portal_anchor():
    q = "Можно ли продлить лицензию без подачи через Госуслуги, на бумажном носителе?"
    text = "### Краткий ответ\nПодайте заявление через Госуслуги."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "единый портал" in low
    assert ("№ 199" in out) or ("№199" in out)


def test_user_mode_rejection_question_adds_article19_anchor():
    q = "Какие основания для отказа в выдаче лицензии?"
    text = "### Краткий ответ\nНужно проверить причины отказа."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "статье 19" in low or "статья 19" in low


def test_user_mode_adds_required_sections_when_missing():
    q = "Какие документы нужны для продления лицензии на алкоголь?"
    text = "Ответ без структуры."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    assert "### Краткий ответ" in out
    assert "### Что сделать заявителю сейчас" in out
    assert "### Какие документы подготовить" in out
    assert "### Что нужно уточнить у заявителя" in out
    assert "### Проверка актуальности норм" in out


def test_user_mode_equipment_list_action_block_is_not_generic():
    q = "Где закреплён перечень видов основного технологического оборудования для лицензирования?"
    text = "### Краткий ответ\nПеречень установлен приказом №405."
    out = app.ensure_user_friendly_answer_with_sources(text, [_mk_match("...")], q)
    low = out.lower()
    assert "№405" in out or "№ 405" in out
    assert "опись оборудования" in low


def test_sources_block_filters_future_placeholder_source():
    rows = [
        (
            1.0,
            {
                "text": "x",
                "metadata": {
                    "doc_type": "Документ",
                    "doc_date_file": "01.01.2026",
                    "source_kind": "guide",
                    "source_file": "future.txt",
                    "doc_title": "8. Документы о подключении к ЕГАИС",
                },
            },
        ),
        _mk_match("...", doc_type="ПРИКАЗ", doc_number="199", source_file="norm_199.rtf"),
    ]
    out = app.sources_block(rows, limit=4)
    assert "01.01.2026" not in out
    assert "№199" in out


def test_sources_block_dedupes_same_source_with_url():
    row = (
        1.0,
        {
            "text": "x",
            "metadata": {
                "doc_type": "ПРИКАЗ",
                "doc_number_text": "199",
                "doc_date_file": "12.08.2019",
                "doc_title": "Об утверждении Административного регламента",
            },
        },
    )
    out = app.sources_block([row, row], limit=4)
    assert out.count("№199") == 1


def _row(cid: str, meta: dict, text: str = "x") -> dict:
    return {
        "chunk_id": cid,
        "text": text,
        "metadata": {"doc_type": "ФЕДЕРАЛЬНЫЙ ЗАКОН", "doc_number_text": "171-ФЗ", **meta},
        "tf": {"x": 1},
        "len": 1,
    }


def test_hierarchy_graph_expands_linear_neighbors():
    rows = {
        "d::c1": _row(
            "d::c1",
            {"neighbor_next_chunk_id": "d::c2", "article_key": "d::ст9", "article_part_index": 1},
        ),
        "d::c2": _row(
            "d::c2",
            {
                "neighbor_prev_chunk_id": "d::c1",
                "neighbor_next_chunk_id": "d::c3",
                "article_key": "d::ст9",
                "article_part_index": 2,
            },
        ),
        "d::c3": _row("d::c3", {"neighbor_prev_chunk_id": "d::c2", "article_key": "d::ст9", "article_part_index": 3}),
    }
    article_map = {"d::ст9": ["d::c1", "d::c2", "d::c3"]}
    matches = [(10.0, rows["d::c2"])]
    out = app._expand_matches_graph(
        matches,
        rows,
        article_map,
        official_only=True,
        neighbor_hops=1,
        max_extra_chunks=10,
        small_article_max_parts=4,
    )
    ids = {app.chunk_row_key(r) for _, r in out}
    assert ids == {"d::c1", "d::c2", "d::c3"}


def test_hierarchy_graph_fills_small_article_gap():
    rows = {
        "d::c1": _row("d::c1", {"article_key": "d::ст5", "article_part_index": 1}),
        "d::c2": _row("d::c2", {"article_key": "d::ст5", "article_part_index": 2}),
    }
    article_map = {"d::ст5": ["d::c1", "d::c2"]}
    matches = [(8.0, rows["d::c1"])]
    out = app._expand_matches_graph(
        matches,
        rows,
        article_map,
        official_only=True,
        neighbor_hops=0,
        max_extra_chunks=10,
        small_article_max_parts=4,
    )
    ids = {app.chunk_row_key(r) for _, r in out}
    assert "d::c2" in ids


def test_chunk_corpus_sequence_metadata():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("chunk_corpus", root / "scripts" / "chunk_corpus.py")
    assert spec and spec.loader
    cc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cc)
    recs = [
        {
            "chunk_id": "doc::chunk_0001",
            "doc_id": "doc",
            "text": "a",
            "metadata": {"doc_type": "ФЕДЕРАЛЬНЫЙ ЗАКОН"},
        },
        {
            "chunk_id": "doc::chunk_0002",
            "doc_id": "doc",
            "text": "b",
            "metadata": {"doc_type": "ФЕДЕРАЛЬНЫЙ ЗАКОН"},
        },
    ]
    cc._link_chunk_sequence(recs, doc_id="doc", block={"article_number": "18", "chapter_title": "Глава 2"})
    m0, m1 = recs[0]["metadata"], recs[1]["metadata"]
    assert m0.get("neighbor_next_chunk_id") == "doc::chunk_0002"
    assert m1.get("neighbor_prev_chunk_id") == "doc::chunk_0001"
    assert m0.get("article_key") == "doc::ст18"
    assert m0.get("article_part_total") == 2
    dense = cc.list_density_score("1) первый пункт\n2) второй пункт\n3) третий пункт")
    assert dense > 0.5


def test_parent_child_expansion_pulls_same_parent_neighbors():
    rows = {
        "d::c1": _row("d::c1", {"article_key": "d::ст18", "article_part_index": 1, "chunk_index": 1}),
        "d::c2": _row("d::c2", {"article_key": "d::ст18", "article_part_index": 2, "chunk_index": 2}),
        "d::c3": _row("d::c3", {"article_key": "d::ст18", "article_part_index": 3, "chunk_index": 3}),
    }
    scored = [(12.0, rows["d::c2"]), (11.0, rows["d::c1"]), (10.0, rows["d::c3"])]
    matches = [(12.0, rows["d::c2"])]
    out = app._expand_matches_parent_child(
        scored,
        matches,
        rows,
        {"article::d::ст18": ["d::c1", "d::c2", "d::c3"]},
        official_only=True,
        top_k=3,
        parent_top_n=3,
        max_extra_chunks=6,
        window=2,
        full_parent_parts=5,
    )
    ids = {app.chunk_row_key(r) for _, r in out}
    assert {"d::c1", "d::c2", "d::c3"} <= ids


def test_query_norm_refs_extracts_article_and_subpoint():
    q = "171-ФЗ статья 19 подпункт 3 какие документы"
    refs = app.query_norm_refs(q)
    assert "171-фз" in refs
    assert "ст19" in refs
    assert "171-фз:ст19" in refs
    assert "пп3" in refs


def test_query_norm_refs_extracts_doc_number():
    q = "Что говорит приказ №199 по срокам?"
    refs = app.query_norm_refs(q)
    assert "199" in refs


def test_parent_child_window_for_list_query_is_wider():
    q = "Где закреплен перечень видов оборудования?"
    assert app.parent_child_window_for_query(q) >= 3
