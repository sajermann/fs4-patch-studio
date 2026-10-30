"""User-facing (Portuguese) text for validation issue codes. Identifiers stay in English; only the
strings shown to the user are pt-BR."""

ISSUE_TEXT = {
    'duplicate_uid': 'Identificador interno repetido ({entity}).',
    'required': 'Campo obrigatório.',
    'invalid_chars': 'Caracteres que o jogo não sabe escrever: {chars}',
    'text_too_long': 'Texto com {length} caracteres; o jogo foi feito para até {limit} (pode ficar cortado).',
    'out_of_range': 'Valor fora da faixa permitida ({min} a {max}).',
    'invalid_date': 'Data inválida (use AAAA-MM-DD).',
    'league_id_out_of_range': 'Id da liga {value} fora da faixa de ids novos ({low} a {high}).',
    'league_id_taken': 'O id {value} já é de outra liga do projeto.',
    'original_league_not_hideable': 'A liga {id} não é uma liga original visível do jogo.',
    'original_team_not_found': 'O time {id} não é um time original do jogo.',
    'original_team_edited_twice': 'O time original {id} já está sendo editado por outra entrada do projeto.',
    'original_team_not_lockable': 'O time {id} não pode ser trancado (o jogo só tranca os times especiais).',
    'stadium_not_lockable': 'O estádio {id} não pode ser trancado.',
    'team_league_hidden': 'A liga deste time está oculta: o time também fica oculto no jogo.',
    'league_image_missing': 'Sem imagem: o seletor de ligas mostra uma silhueta.',
    'too_many_leagues': 'No máximo {max} ligas novas (cada uma usa um número de imagem livre do jogo).',
    'league_too_many_teams': 'A liga {league} tem {count} times; o máximo é {max} (com mais, a tela de escolha de '
                             'times do jogo não carrega todos os escudos).',
    'league_not_found': 'Liga não encontrada.',
    'league_hidden': 'Essa liga original não aparece no seletor do jogo.',
    'template_not_found': 'Molde {id} não existe no banco do jogo.',
    'template_not_generic': 'O molde {id} tem cabeça escaneada; o visual escolhido pode ser ignorado.',
    'crest_missing': 'Imagem do escudo não encontrada ({path}).',
    'crest_required': 'Envie um escudo.',
    'team_id_out_of_range': 'Id do time {value} fora da faixa de ids novos ({low} a {high}).',
    'team_id_in_game': 'O id {value} já é de um time do jogo.',
    'team_id_taken': 'O id {value} já é de outro time do projeto.',
    'roster_empty': 'O time precisa de pelo menos 1 jogador.',
    'roster_too_large': 'Elenco com {count} jogadores; o máximo é {max}.',
    'captain_not_in_roster': 'O capitão precisa ser um jogador do time.',
    'taker_not_in_roster': 'O cobrador precisa ser um jogador do time.',
    'lineup_mode_invalid': 'Modo de jogo inválido na escalação ({players} jogadores).',
    'lineup_mode_repeated': 'Escalação repetida para o modo de {players} jogadores.',
    'lineup_tactic_invalid': 'Tática que o modo de {players} jogadores não tem.',
    'lineup_too_many_starters': '{count} titulares; o modo tem {max} vagas.',
    'lineup_player_repeated': 'Jogador repetido entre os titulares (modo de {players}).',
    'lineup_player_not_in_roster': 'A escalação (modo de {players}) cita jogador que não está mais no time; a vaga é preenchida com o próximo do elenco.',
    'lineup_goalkeeper_not_gk': '{player} não é goleiro e está na vaga de GOL (modo de {players}); o jogo aceita.',
    'duplicate_number': 'Número {number} repetido no elenco.',
    'free_agent_not_exported': 'Jogador avulso: fica só no app até entrar num time.',
    'team_not_found': 'Time não encontrado.',
    'player_team_repeated': 'O jogador já está neste time (em outra linha).',
    'team_full': 'O time fica com {count} jogadores; o máximo é {max}. Tire alguém do time.',
    'original_player_not_found': 'O jogador {id} não é um jogador original do jogo.',
    'original_player_edited_twice': 'O jogador original {id} já está sendo editado por outra entrada do projeto.',
    'face_needs_six_digits': 'Face real só em jogador com id de 6 dígitos (este é {id}); use a cabeça genérica ou a do jogo.',
    'invalid_position': 'Posição inválida.',
    'unknown_skill': 'Habilidade desconhecida.',
    'unknown_field': 'Campo desconhecido.',
    'invalid_appearance': 'Código de visual que nenhum jogador genérico do jogo usa.',
    'invalid_street_piece': 'Peça do uniforme de rua que não existe no jogo.',
    'real_kit_missing': 'Sem uniforme real neste slot: vai o uniforme genérico (cor sólida + escudo).',
    'real_kit_file_required': 'Envie a camisa e o calção (sem os dois, o slot não é usado).',
    'real_kit_file_missing': 'Imagem não encontrada ({path}).',
    'real_kit_bad_size': 'Imagem de {width}×{height}; o esperado é {expected} (ou outro tamanho na mesma proporção).',
    'real_kit_small': 'Imagem pequena ({width}×{height}): o jogo usa 1024, vai ficar borrada.',
    'photo_missing': 'Imagem da foto não encontrada ({path}).',
    'face_missing': 'Jogador não genérico sem face: escolha uma face real na aba Visual (ou marque “genérico”).',
    'face_files_missing': 'Arquivos da face {id} não encontrados na pasta do projeto; escolha a face de novo.',
    'player_id_out_of_range': 'Id do jogador {value} fora da faixa de ids novos ({low} a {high}).',
    'player_id_taken': 'O id {value} já é de outro jogador do projeto.',
}


def issue_text(issue):
    template = ISSUE_TEXT.get(issue.code, issue.code)
    try:
        return template.format(entity=issue.entity, **issue.params)
    except (KeyError, IndexError):
        return template


def issue_json(issue):
    data = issue.to_json()
    data['message'] = issue_text(issue)
    return data
