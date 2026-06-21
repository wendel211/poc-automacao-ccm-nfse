from src.services.bh_fic import _extract_ccm


def test_extract_ccm_prefers_active_registration_for_same_cnpj():
    text = """
    Inscricao Municipal
    02433830014
    DIAS COSTA
    10.999.280/0001-47
    Situacao
    BAIXADA
    Inscricao Municipal
    02433830022
    DIAS COSTA
    10.999.280/0001-47
    Situacao
    ATIVA
    """

    assert _extract_ccm(text, "10999280000147") == "02433830022"


def test_extract_ccm_prefers_active_registration_in_fic_table_row():
    text = """
    Inscrição Situação
    Nome CNPJ/CPF Endereço cadastrado
    Municipal IM
    02433830014 DIAS COSTA 10999280000147 AVENIDA,RAJA GABAGLIA,1617,ANDAR BAIXADA
    SOCIEDADE DE 7,LUXEMBURGO,BELO HORIZONTE,MINAS
    ADVOGADOS GERAIS
    02433830022 DIAS COSTA 10999280000147 RUA,DA BAHIA,888,SALA 1,CENTRO,BELO ATIVA
    SOCIEDADE DE HORIZONTE,MINAS GERAIS
    ADVOGADOS
    """

    assert _extract_ccm(text, "10999280000147") == "02433830022"


def test_extract_ccm_keeps_legacy_fallback_when_status_is_absent():
    text = """
    Inscricao Municipal
    10380110013
    FARIA LTDA
    28.203.865/0001-74
    """

    assert _extract_ccm(text, "28203865000174") == "10380110013"
