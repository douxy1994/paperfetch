"""Verify PDF identity and exact current-converter passthrough, not OCR quality."""


def verified_pdf_passthrough_article(fixture):
    from unittest import mock
    import pymupdf
    from tests import golden_corpus

    body = fixture.raw_path.read_bytes()
    with pymupdf.open(stream=body, filetype="pdf") as document:
        assert not document.needs_pass
        assert not document.is_repaired
        assert document.page_count > 0
        assert all(
            document.load_page(i).rect.width > 0 for i in range(document.page_count)
        )
    converted = []
    original = golden_corpus.pdf_fetch_result_from_bytes

    def verified(**kwargs):
        kwargs["expected_identity"] = {"doi": fixture.doi, "title": fixture.title}
        result = original(**kwargs)
        assert result.diagnostics["identity"]["status"] == "match"
        converted.append(result.markdown_text)
        return result

    with mock.patch.object(
        golden_corpus, "pdf_fetch_result_from_bytes", side_effect=verified
    ):
        article = golden_corpus.build_article_from_fixture(fixture)
    assert len(converted) == 1
    assert converted[0]
    assert article.sections[0].text == converted[0]
    assert article.references == []
    assert article.to_dict()["sections"][0]["text"] == converted[0]
    assert converted[0] in article.to_ai_markdown(
        include_refs="all", max_tokens="full_text"
    )

    return article
