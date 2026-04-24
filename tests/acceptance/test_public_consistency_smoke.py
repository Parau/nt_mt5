import pathlib
import pytest

# Caminhos dos arquivos principais
ROOT_DIR = pathlib.Path(__file__).parent.parent.parent
README_PATH = ROOT_DIR / "README.md"
EXAMPLES_DIR = ROOT_DIR / "examples"

def test_readme_terminal_access_terminology():
    """
    Valida que o README utiliza a terminologia arquitetural correta para acesso ao terminal.
    """
    assert README_PATH.exists(), f"README.md não encontrado em {README_PATH}"
    content = README_PATH.read_text()

    # EXTERNAL_RPYC deve ser apresentado como suportado atualmente
    assert "EXTERNAL_RPYC" in content
    assert "Currently Supported" in content or "suportado" in content.lower()

    # MANAGED_TERMINAL deve ser apresentado como planejado
    assert "MANAGED_TERMINAL" in content
    assert "Planned" in content or "planejado" in content.lower()

    # DOCKERIZED deve ser tratado como backend/estratégia interna, não como modo de acesso principal
    # (No README atual ele aparece como 'internal strategy')
    assert "DOCKERIZED" in content
    assert "internal strategy" in content.lower() or "backend" in content.lower()

    # Reforço: DOCKERIZED não deve ser listado como um MT5TerminalAccessMode de primeiro nível
    # na documentação pública (README)
    assert "MT5TerminalAccessMode.DOCKERIZED" not in content
    # O README deve deixar claro que os modos são EXTERNAL_RPYC e MANAGED_TERMINAL
    assert "EXTERNAL_RPYC" in content
    assert "MANAGED_TERMINAL" in content

def test_example_external_rpyc_consistency():
    """
    Valida que o exemplo de external_rpyc reflete o caminho público atual.
    """
    example_path = EXAMPLES_DIR / "connect_with_external_rpyc.py"
    assert example_path.exists(), f"Exemplo não encontrado em {example_path}"
    content = example_path.read_text()

    # Deve usar o modo EXTERNAL_RPYC
    assert "MT5TerminalAccessMode.EXTERNAL_RPYC" in content
    # Não deve usar managed_terminal neste exemplo
    assert "managed_terminal=" not in content or "managed_terminal=None" in content

def test_example_dockerized_consistency():
    """
    Valida que o exemplo dockerized é tratado como MANAGED_TERMINAL e placeholder.
    """
    example_path = EXAMPLES_DIR / "connect_with_dockerized_terminal.py"
    assert example_path.exists(), f"Exemplo não encontrado em {example_path}"
    content = example_path.read_text()

    # Deve usar MANAGED_TERMINAL
    assert "MT5TerminalAccessMode.MANAGED_TERMINAL" in content
    # Deve usar backend DOCKERIZED
    assert "ManagedTerminalBackend.DOCKERIZED" in content

    # Deve conter avisos de que é um placeholder / sob construção
    assert "UNDER CONSTRUCTION" in content or "placeholder" in content.lower()
    assert "RuntimeError" in content

def test_no_conflicting_public_terminology():
    """
    Verifica a ausência de terminologia conflitante que promova dockerized a modo principal.
    """
    # Verifica README e exemplos principais
    files_to_check = [
        README_PATH,
        EXAMPLES_DIR / "connect_with_external_rpyc.py",
        EXAMPLES_DIR / "connect_with_dockerized_terminal.py",
    ]

    for file_path in files_to_check:
        if not file_path.exists():
            continue
        content = file_path.read_text()

        # Não deve haver menção a 'DOCKERIZED' como um MT5TerminalAccessMode diretamente
        # A forma correta é MT5TerminalAccessMode.MANAGED_TERMINAL
        assert "MT5TerminalAccessMode.DOCKERIZED" not in content

        # Não deve haver menção a 'dockerized_gateway' como parâmetro de alto nível sendo promovido
        # (Embora possa existir no código para compatibilidade, não deve ser o foco da doc/examples)
        # No README atual não há, nos exemplos também não deve haver como forma principal.
        assert "dockerized_gateway=" not in content or "#" in content.split("dockerized_gateway=")[0].split("\n")[-1]

def test_managed_terminal_not_promoted_as_complete():
    """
    Garante que managed_terminal não seja tratado como funcionalidade concluída.
    """
    content = README_PATH.read_text()

    # Procura por trechos que indiquem que MANAGED_TERMINAL está pronto
    # No README está como "Planned" e "under development"
    assert "MANAGED_TERMINAL" in content
    managed_section = content.split("MANAGED_TERMINAL")[1].split("##")[0]
    assert "not yet operational" in managed_section.lower() or "under development" in managed_section.lower()
