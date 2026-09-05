from pathlib import Path


WORKFLOW = Path(".github/workflows/generisi-raspored.yml")


def test_hint_ide_prvo_sa_head_grane_pa_sa_main_i_iskljucuje_tekuci_run():
    tekst = WORKFLOW.read_text(encoding="utf-8")

    head = 'preuzmi_runove_grane "${GITHUB_HEAD_BRANCH}"'
    fallback = "preuzmi_runove_grane main"
    assert head in tekst and fallback in tekst
    assert tekst.index(head) < tekst.index(fallback)
    assert "status=success" in tekst
    assert "select(.id != ${CURRENT_RUN_ID})" in tekst


def test_workflow_ima_eksplicitni_hladni_start_sa_default_false():
    tekst = WORKFLOW.read_text(encoding="utf-8")

    assert "prisilni_hladni_start:" in tekst
    assert "default: false" in tekst
    assert 'if [ "${FORCE_COLD}" = "true" ]' in tekst
    assert "preskačem sve artefakte" in tekst
