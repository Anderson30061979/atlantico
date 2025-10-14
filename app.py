import streamlit as st
import pandas as pd
from itertools import combinations
from datetime import datetime
import sqlalchemy
import re

# --- Configuração da Página ---
st.set_page_config(
    page_title="Sistema de Ranking de Tênis",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Conexão com o Banco de Dados SQLite ---
# Isto cria um ficheiro ranking.db na mesma pasta se ele não existir.
conn = st.connection('ranking_db', type='sql', url='sqlite:///ranking.db')


# --- Funções do Banco de Dados ---

def criar_tabelas_se_nao_existir():
    """Cria as tabelas no banco de dados na primeira execução."""
    with conn.session as s:
        s.execute(sqlalchemy.text('''
            CREATE TABLE IF NOT EXISTS jogadores (
                Nome TEXT PRIMARY KEY,
                Classe TEXT
            );
        '''))
        s.execute(sqlalchemy.text('''
            CREATE TABLE IF NOT EXISTS jogos (
                "index" INTEGER PRIMARY KEY AUTOINCREMENT,
                Classe TEXT,
                "Jogador 1" TEXT,
                "Jogador 2" TEXT,
                Resultado TEXT,
                Status TEXT,
                Detalhes TEXT
            );
        '''))
        s.execute(sqlalchemy.text('''
            CREATE TABLE IF NOT EXISTS ciclo_info (
                id INTEGER PRIMARY KEY CHECK (id = 1), -- Garante apenas uma linha
                ciclo_ativo BOOLEAN,
                inicio TEXT,
                fim TEXT
            );
        '''))
        s.commit()


def carregar_dados():
    """Carrega todos os dados do SQLite para o session_state."""
    with st.spinner("A carregar dados do banco de dados..."):
        st.session_state.jogadores = conn.query('SELECT * FROM jogadores;', ttl=5)
        st.session_state.jogos = conn.query('SELECT * FROM jogos;', ttl=5)

        # CORREÇÃO: Inicializa o dicionário antes de tentar adicionar valores a ele.
        st.session_state.ciclo_info = {}
        
        ciclo_info_df = conn.query('SELECT * FROM ciclo_info WHERE id = 1;', ttl=5)
        if not ciclo_info_df.empty:
            st.session_state.ciclo_ativo = bool(ciclo_info_df.iloc[0]['ciclo_ativo'])
            st.session_state.ciclo_info['inicio'] = pd.to_datetime(ciclo_info_df.iloc[0]['inicio']) if pd.notna(
                ciclo_info_df.iloc[0]['inicio']) else None
            st.session_state.ciclo_info['fim'] = pd.to_datetime(ciclo_info_df.iloc[0]['fim']) if pd.notna(
                ciclo_info_df.iloc[0]['fim']) else None
        else:  # Se a tabela estiver vazia, inicializa os valores padrão
            st.session_state.ciclo_ativo = False
            st.session_state.ciclo_info = {"inicio": None, "fim": None}


def salvar_jogadores():
    """Apaga os jogadores antigos e salva o novo dataframe no SQLite."""
    try:
        with st.spinner("A guardar jogadores no banco de dados..."):
            with conn.session as s:
                s.execute(sqlalchemy.text('DELETE FROM jogadores;'))
                st.session_state.jogadores.to_sql('jogadores', s.connection(), if_exists='append', index=False)
                s.commit()
        st.toast("Lista de jogadores guardada!", icon="✅")
    except Exception as e:
        st.error(f"Não foi possível guardar os jogadores. Erro: {e}")


def salvar_jogos():
    """Apaga os jogos antigos e salva o novo dataframe no SQLite."""
    try:
        with st.spinner("A atualizar os jogos no banco de dados..."):
            with conn.session as s:
                s.execute(sqlalchemy.text('DELETE FROM jogos;'))
                st.session_state.jogos.to_sql('jogos', s.connection(), if_exists='append', index=False)
                s.commit()
        st.toast("Tabela de jogos guardada!", icon="📅")
    except Exception as e:
        st.error(f"Não foi possível guardar os jogos. Erro: {e}")


def salvar_ciclo_info():
    """Salva (ou atualiza) o estado do ciclo no SQLite."""
    try:
        with st.spinner("A guardar informações do ciclo..."):
            info_para_salvar = {
                'id': 1,
                'ciclo_ativo': st.session_state.ciclo_ativo,
                'inicio': str(st.session_state.ciclo_info.get('inicio')),
                'fim': str(st.session_state.ciclo_info.get('fim')),
            }
            df_info = pd.DataFrame([info_para_salvar])
            with conn.session as s:
                s.execute(sqlalchemy.text('DELETE FROM ciclo_info;'))
                df_info.to_sql('ciclo_info', s.connection(), if_exists='append', index=False)
                s.commit()
        st.toast("Informações do ciclo guardadas!", icon="ℹ️")
    except Exception as e:
        st.error(f"Não foi possível guardar as informações do ciclo. Erro: {e}")


def inicializar_session_state():
    if 'dados_carregados' not in st.session_state:
        carregar_dados()
        st.session_state.dados_carregados = True
    if 'editing_game_index' not in st.session_state:
        st.session_state.editing_game_index = None

def exibir_dashboard_ciclo():
    """Mostra as métricas principais do ciclo atual."""
    if not st.session_state.get('ciclo_ativo', False):
        return

    st.subheader("📊 Dados dos Jogos do Ciclo Atual")

    info = st.session_state.ciclo_info
    inicio_str = info.get('inicio').strftime('%d/%m/%Y') if info.get('inicio') else 'N/D'
    fim_str = info.get('fim').strftime('%d/%m/%Y') if info.get('fim') else 'N/D'
    st.write(f"**Período:** {inicio_str} a {fim_str}")

    total_jogos = len(st.session_state.jogos)
    if total_jogos > 0:
        jogos_concluidos = len(st.session_state.jogos[st.session_state.jogos['Status'] != 'Pendente'])
        percent_concluido = (jogos_concluidos / total_jogos * 100)
    else:
        jogos_concluidos = 0
        percent_concluido = 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Partidas", f"{total_jogos}")
    col2.metric("Partidas Concluídas", f"{jogos_concluidos}")
    col3.metric("Progresso do Ciclo", f"{percent_concluido:.1f}%")

    st.progress(percent_concluido / 100)
    st.divider()

def gerar_tabela_jogos_por_classe(classe):
    jogadores_classe = st.session_state.jogadores[st.session_state.jogadores['Classe'] == classe]['Nome'].tolist()
    if len(jogadores_classe) < 2: return pd.DataFrame()
    confrontos = list(combinations(jogadores_classe, 2))
    jogos_df = pd.DataFrame(confrontos, columns=['Jogador 1', 'Jogador 2'])
    jogos_df['Classe'] = classe
    jogos_df['Resultado'] = '-'
    jogos_df['Status'] = 'Pendente'
    jogos_df['Detalhes'] = ''
    return jogos_df


def calcular_ranking():
    if st.session_state.jogos.empty or st.session_state.jogadores.empty:
        st.session_state.ranking = pd.DataFrame()
        return
    jogos_finalizados = st.session_state.jogos[st.session_state.jogos['Status'].isin(['Finalizado', 'W.O.'])].copy()
    ranking_data = {
        nome: {'Pontos': 0, 'Jogos': 0, 'Vitorias': 0, 'Derrotas': 0, 'Sets Vencidos': 0, 'Sets Perdidos': 0,
               'Classe': st.session_state.jogadores.loc[st.session_state.jogadores['Nome'] == nome, 'Classe'].iloc[0]}
        for nome in st.session_state.jogadores['Nome']}
    for _, jogo in jogos_finalizados.iterrows():
        j1, j2, resultado = jogo['Jogador 1'], jogo['Jogador 2'], jogo['Resultado']
        if resultado == '-' or resultado == '0x0' or not isinstance(resultado, str): continue
        sets_j1, sets_j2 = map(int, resultado.split('x'))
        if j1 not in ranking_data or j2 not in ranking_data: continue
        ranking_data[j1]['Jogos'] += 1;
        ranking_data[j2]['Jogos'] += 1
        ranking_data[j1]['Sets Vencidos'] += sets_j1;
        ranking_data[j1]['Sets Perdidos'] += sets_j2
        ranking_data[j2]['Sets Vencidos'] += sets_j2;
        ranking_data[j2]['Sets Perdidos'] += sets_j1
        if sets_j1 > sets_j2:
            ranking_data[j1]['Vitorias'] += 1;
            ranking_data[j2]['Derrotas'] += 1
            ranking_data[j1]['Pontos'] += 3 if sets_j2 == 0 else 2
            if sets_j2 == 1: ranking_data[j2]['Pontos'] += 1
        elif sets_j2 > sets_j1:
            ranking_data[j2]['Vitorias'] += 1;
            ranking_data[j1]['Derrotas'] += 1
            ranking_data[j2]['Pontos'] += 3 if sets_j1 == 0 else 2
            if sets_j1 == 1: ranking_data[j1]['Pontos'] += 1
    if not ranking_data: st.session_state.ranking = pd.DataFrame(); return
    ranking_df = pd.DataFrame.from_dict(ranking_data, orient='index')
    ranking_df['Saldo de Sets'] = ranking_df['Sets Vencidos'] - ranking_df['Sets Perdidos']
    ranking_df = ranking_df.reset_index().rename(columns={'index': 'Nome'})
    ranking_df = ranking_df.sort_values(by=['Classe', 'Pontos', 'Saldo de Sets'], ascending=[True, False, False])
    st.session_state.ranking = ranking_df.reset_index(drop=True)


def pagina_ranking():
    st.header("🏆 Ranking Atual - Atântico Tênis Clube")
    exibir_dashboard_ciclo()
    
    if 'ranking' not in st.session_state or st.session_state.ranking.empty: calcular_ranking()
    if st.session_state.ranking.empty: st.info("O ranking será exibido aqui."); return
    classes_validas = [c for c in st.session_state.ranking['Classe'].unique() if pd.notna(c)]
    for classe in sorted(classes_validas):
        st.subheader(f"Classe {classe}")
        ranking_classe = st.session_state.ranking[st.session_state.ranking['Classe'] == classe].copy()
        ranking_classe.insert(0, 'Posição', range(1, len(ranking_classe) + 1))
        st.dataframe(ranking_classe[['Posição', 'Nome', 'Pontos', 'Jogos', 'Vitorias', 'Derrotas', 'Saldo de Sets']],
                     use_container_width=True, hide_index=True)


def pagina_tabela_de_jogos():
    st.header("📅 Tabela de Jogos")
    editing_index = st.session_state.get('editing_game_index')
    if editing_index is not None:
        st.subheader("✏️ Editando Resultado do Jogo")
        form_registro(None, None, index_jogo_editar=editing_index)
        if st.button("Cancelar Edição"): st.session_state.editing_game_index = None; st.rerun()
        return
    if not st.session_state.ciclo_ativo: st.warning("O ciclo de jogos não está ativo."); return

    if st.session_state.jogos.empty:
        st.info("Ainda não há jogos neste ciclo.")
        return

    classes = sorted(st.session_state.jogos['Classe'].unique())
    for classe in classes:
        st.subheader(f"Jogos da Classe {classe}")
        jogos_classe_df = st.session_state.jogos[st.session_state.jogos['Classe'] == classe].copy()
        st.dataframe(jogos_classe_df[['Jogador 1', 'Jogador 2', 'Resultado', 'Detalhes', 'Status']], hide_index=True,
                     use_container_width=True)
        with st.expander("Registrar Novo Resultado", expanded=False):
            jogos_pendentes = jogos_classe_df[jogos_classe_df['Status'] == 'Pendente']
            if not jogos_pendentes.empty:
                form_registro(jogos_pendentes, classe)
            else:
                st.success("Todos os jogos desta classe foram finalizados!")
        with st.expander("Gerenciar Resultados Lançados"):
            jogos_finalizados = jogos_classe_df[jogos_classe_df['Status'] != 'Pendente']
            if not jogos_finalizados.empty:
                opts = jogos_finalizados.apply(lambda x: f"{x['Jogador 1']} vs {x['Jogador 2']}", axis=1)
                jogo_sel_str = st.selectbox("Selecione um jogo", options=opts, index=None, key=f"sel_{classe}")
                if jogo_sel_str:
                    j1, j2 = jogo_sel_str.split(' vs ')
                    idx = jogos_finalizados[
                        (jogos_finalizados['Jogador 1'] == j1) & (jogos_finalizados['Jogador 2'] == j2)].index[0]
                    col1, col2 = st.columns(2)
                    if col1.button("✏️ Editar", key=f"ed_{idx}"): st.session_state.editing_game_index = idx; st.rerun()
                    if col2.button("🔄 Desfazer", key=f"un_{idx}"):
                        st.session_state.jogos.loc[idx, ['Resultado', 'Status', 'Detalhes']] = ['-', 'Pendente', '']
                        salvar_jogos();
                        calcular_ranking();
                        st.rerun()


def form_registro(jogos_pendentes, classe, index_jogo_editar=None):
    is_edit = index_jogo_editar is not None
    def_scores, def_stb = [''] * 6, False
    if is_edit:
        jogo = st.session_state.jogos.loc[index_jogo_editar]
        classe, detalhes = jogo['Classe'], jogo['Detalhes']
        if isinstance(detalhes, str) and 'W.O.' not in detalhes and 'Dupla' not in detalhes:
            nums = re.findall(r'\d+', detalhes);
            if len(nums) >= 4: def_scores[:4] = nums[:4]
            if len(nums) == 6: def_scores[4:], def_stb = nums[4:], True
    key_sufix = f"_{classe}_{'edit' if is_edit else 'new'}_{index_jogo_editar or ''}"
    with st.form(key=f'form_res{key_sufix}'):
        if is_edit:
            st.info(f"Editando: **{jogo['Jogador 1']} vs {jogo['Jogador 2']}**")
        else:
            jogo_sel_str = st.selectbox("Selecione o Jogo",
                                        options=jogos_pendentes.apply(lambda x: f"{x['Jogador 1']} vs {x['Jogador 2']}",
                                                                      axis=1), index=None)
        c1, c2 = st.columns(2)
        s1j1 = c1.text_input("Set 1 - J1", value=def_scores[0]);
        s1j2 = c2.text_input("Set 1 - J2", value=def_scores[1])
        s2j1 = c1.text_input("Set 2 - J1", value=def_scores[2]);
        s2j2 = c2.text_input("Set 2 - J2", value=def_scores[3])
        stb = st.checkbox("3º set (Super Tie-break)?", value=def_stb)
        s3j1, s3j2 = '0', '0'
        if stb: s3j1 = c1.text_input("STB J1", value=def_scores[4]); s3j2 = c2.text_input("STB J2", value=def_scores[5])
        if st.form_submit_button("Salvar"):
            try:
                if not all([s1j1, s1j2, s2j1, s2j2]) or (stb and not all([s3j1, s3j2])): st.error(
                    "Preencha todos os campos."); return
                scores = list(map(int, [s1j1, s1j2, s2j1, s2j2, s3j1, s3j2]))
                s1, s2 = (scores[0] > scores[1]) + (scores[2] > scores[3]) + (scores[4] > scores[5]), (
                            scores[1] > scores[0]) + (scores[3] > scores[2]) + (scores[5] > scores[4])
                if max(s1, s2) != 2: st.error("Placar inválido."); return
                res, det = f"{s1}x{s2}", f"{scores[0]}x{scores[1]}, {scores[2]}x{scores[3]}"
                if stb: det += f", {scores[4]}x{scores[5]} (STB)"
                if is_edit:
                    idx = index_jogo_editar
                else:
                    if not jogo_sel_str: st.error("Selecione um jogo."); return
                    j1, j2 = jogo_sel_str.split(' vs ');
                    idx = \
                    jogos_pendentes[(jogos_pendentes['Jogador 1'] == j1) & (jogos_pendentes['Jogador 2'] == j2)].index[
                        0]
                st.session_state.jogos.loc[idx, ['Resultado', 'Detalhes', 'Status']] = [res, det, 'Finalizado']
                if is_edit: st.session_state.editing_game_index = None
                salvar_jogos();
                calcular_ranking();
                st.rerun()
            except (ValueError, TypeError):
                st.error("Placar deve conter apenas números.")


def pagina_administracao():
    st.header("⚙️ Painel do Administrador")
    st.subheader("Gestão de Ciclos")
    if not st.session_state.ciclo_ativo:
        with st.form("form_novo_ciclo"):
            c1, c2 = st.columns(2);
            data_inicio = c1.date_input("Início");
            data_fim = c2.date_input("Fim")
            if st.form_submit_button("🚀 Iniciar Novo Ciclo"):
                if len(st.session_state.jogadores) < 2: st.warning("Cadastre pelo menos 2 jogadores."); return
                classes = st.session_state.jogadores['Classe'].dropna().unique()
                tabelas = [gerar_tabela_jogos_por_classe(c) for c in classes]
                if not tabelas: st.error("Nenhuma classe tem jogadores suficientes."); return
                st.session_state.jogos = pd.concat(tabelas, ignore_index=True)
                st.session_state.ciclo_ativo, st.session_state.ciclo_info = True, {"inicio": data_inicio,
                                                                                   "fim": data_fim}
                salvar_jogos();
                salvar_ciclo_info();
                st.success("Novo ciclo iniciado!");
                st.rerun()
    if st.button("🏁 Fechar Ciclo", disabled=not st.session_state.ciclo_ativo,
                 type="primary"): st.session_state.show_fechar_ciclo = True
    if st.session_state.get('show_fechar_ciclo'): handle_fechar_ciclo()
    st.divider()
    st.subheader("Gestão de Jogadores")
    jog_edit_df = st.data_editor(st.session_state.jogadores, num_rows="dynamic", use_container_width=True)
    if st.button("Salvar Jogadores"):
        jog_final = jog_edit_df.dropna(subset=['Nome', 'Classe']);
        jog_final = jog_final[jog_final['Nome'] != '']
        st.session_state.jogadores = jog_final.reset_index(drop=True);
        salvar_jogadores();
        st.rerun()


def handle_fechar_ciclo():
    jogos_pendentes = st.session_state.jogos[st.session_state.jogos['Status'] == 'Pendente']
    if not jogos_pendentes.empty:
        st.subheader("Resolver Jogos Pendentes");
        for idx, jogo in jogos_pendentes.iterrows():
            j1, j2 = jogo['Jogador 1'], jogo['Jogador 2']
            c = st.columns([3, 1, 1, 1]);
            c[0].write(f"**{j1} vs {j2}**")
            if c[1].button(f"W.O. {j1}", key=f"wo1_{idx}"):
                st.session_state.jogos.loc[idx, ['Resultado', 'Detalhes', 'Status']] = ['2x0', 'W.O.', 'W.O.'];
                salvar_jogos();
                st.rerun()
            if c[2].button(f"W.O. {j2}", key=f"wo2_{idx}"):
                st.session_state.jogos.loc[idx, ['Resultado', 'Detalhes', 'Status']] = ['0x2', 'W.O.', 'W.O.'];
                salvar_jogos();
                st.rerun()
            if c[3].button("Derrota Dupla", key=f"dd_{idx}"):
                st.session_state.jogos.loc[idx, ['Resultado', 'Detalhes', 'Status']] = ['0x0', 'Derrota Dupla',
                                                                                        'Finalizado'];
                salvar_jogos();
                st.rerun()
    else:
        st.success("Todos os jogos finalizados!")
        if st.button("Confirmar Fechamento do Ciclo"):
            calcular_ranking()
            ranking_final, jog_atualizado = st.session_state.ranking.copy(), st.session_state.jogadores.copy().set_index(
                'Nome')
            classes = sorted([c for c in ranking_final['Classe'].unique() if pd.notna(c)])
            for i, classe in enumerate(classes):
                ranking_classe = ranking_final[ranking_final['Classe'] == classe].sort_values(
                    by=['Pontos', 'Saldo de Sets'], ascending=False)
                if i < len(classes) - 1 and len(ranking_classe) > 2:
                    for j in ranking_classe.tail(2)['Nome'].tolist(): jog_atualizado.loc[j, 'Classe'] = classes[i + 1]
                if i > 0 and len(ranking_classe) > 2:
                    for j in ranking_classe.head(2)['Nome'].tolist(): jog_atualizado.loc[j, 'Classe'] = classes[i - 1]
            st.session_state.jogadores = jog_atualizado.reset_index()
            st.session_state.ciclo_ativo, st.session_state.show_fechar_ciclo = False, False
            st.session_state.jogos = st.session_state.jogos.iloc[0:0]  # Limpa o dataframe
            salvar_jogadores();
            salvar_jogos();
            salvar_ciclo_info()
            st.success("Ciclo fechado!");
            st.balloons();
            st.rerun()


def main():
    criar_tabelas_se_nao_existir()  # Garante que as tabelas existem antes de qualquer coisa
    inicializar_session_state()
    st.sidebar.title("🎾 Menu de Navegação")
    status_ciclo = 'Ativo' if st.session_state.ciclo_ativo else 'Inativo'
    st.sidebar.info(f"Ciclo Atual: **{status_ciclo}**")
    paginas = {"Ranking": pagina_ranking, "Tabela de Jogos": pagina_tabela_de_jogos,
               "Administração": pagina_administracao}
    selecao = st.sidebar.radio("Escolha uma página", list(paginas.keys()))
    paginas[selecao]()


if __name__ == "__main__":
    main()

