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

# --- Conexão com o Banco de Dados Supabase ---
# As credenciais são lidas de .streamlit/secrets.toml
try:
    conn = st.connection("supabase", type="sql")
except Exception as e:
    st.error("Não foi possível conectar ao banco de dados. Verifique os 'Secrets' da sua aplicação.")
    st.stop()


# --- Funções do Banco de Dados ---

def carregar_dados():
    """Carrega todos os dados do Supabase para o session_state."""
    with st.spinner("A carregar dados do banco de dados..."):
        # CORREÇÃO: Simplificada a consulta para maior compatibilidade. A ordenação será feita depois.
        st.session_state.jogadores = conn.query('SELECT * FROM jogadores;', ttl=10)
        st.session_state.jogos = conn.query('SELECT * FROM jogos;', ttl=10)
        
        if 'Data' in st.session_state.jogos.columns:
            st.session_state.jogos['Data'] = pd.to_datetime(st.session_state.jogos['Data'], errors='coerce')

        st.session_state.ciclo_info = {}
        ciclo_info_df = conn.query('SELECT * FROM ciclo_info WHERE id = 1;', ttl=10)
        
        if not ciclo_info_df.empty:
            st.session_state.ciclo_ativo = bool(ciclo_info_df.iloc[0]['ciclo_ativo'])
            st.session_state.ciclo_info['inicio'] = pd.to_datetime(ciclo_info_df.iloc[0]['inicio']) if pd.notna(ciclo_info_df.iloc[0]['inicio']) else None
            st.session_state.ciclo_info['fim'] = pd.to_datetime(ciclo_info_df.iloc[0]['fim']) if pd.notna(ciclo_info_df.iloc[0]['fim']) else None
        else:
            st.session_state.ciclo_ativo = False
            st.session_state.ciclo_info = {"inicio": None, "fim": None}

def salvar_jogadores():
    """Salva o dataframe de jogadores no Supabase."""
    try:
        with st.spinner("A guardar jogadores..."):
            with conn.session as s:
                # CORREÇÃO: Usando DELETE que é mais padrão que TRUNCATE.
                s.execute(sqlalchemy.text('DELETE FROM jogadores;'))
                st.session_state.jogadores.to_sql('jogadores', s.connection(), if_exists='append', index=False)
                s.commit()
        st.toast("Lista de jogadores guardada!", icon="✅")
    except Exception as e:
        st.error(f"Não foi possível guardar os jogadores. Erro: {e}")

def salvar_jogos():
    """Salva o dataframe de jogos no Supabase."""
    try:
        with st.spinner("A atualizar jogos..."):
            with conn.session as s:
                # CORREÇÃO: Usando DELETE que é mais padrão que TRUNCATE.
                s.execute(sqlalchemy.text('DELETE FROM jogos;'))
                st.session_state.jogos.to_sql('jogos', s.connection(), if_exists='append', index=False)
                s.commit()
        st.toast("Tabela de jogos guardada!", icon="📅")
    except Exception as e:
        st.error(f"Não foi possível guardar os jogos. Erro: {e}")

def salvar_ciclo_info():
    """Salva o estado do ciclo no Supabase."""
    try:
        with st.spinner("A guardar informações do ciclo..."):
            info_para_salvar = {
                'id': 1,
                'ciclo_ativo': st.session_state.ciclo_ativo,
                'inicio': st.session_state.ciclo_info.get('inicio'),
                'fim': st.session_state.ciclo_info.get('fim'),
            }
            df_info = pd.DataFrame([info_para_salvar])
            with conn.session as s:
                s.execute(sqlalchemy.text('DELETE FROM ciclo_info WHERE id=1;'))
                df_info.to_sql('ciclo_info', s.connection(), if_exists='append', index=False)
                s.commit()
        st.toast("Informações do ciclo guardadas!", icon="ℹ️")
    except Exception as e:
        st.error(f"Não foi possível guardar as informações do ciclo. Erro: {e}")


# --- Restante do código (Lógica da UI) ---

def inicializar_session_state():
    if 'dados_carregados' not in st.session_state:
        carregar_dados()
        # Ordena os jogadores aqui, depois de carregar
        st.session_state.jogadores = st.session_state.jogadores.sort_values(by="Nome").reset_index(drop=True)
        st.session_state.dados_carregados = True
    if 'editing_game_index' not in st.session_state:
        st.session_state.editing_game_index = None

def exibir_dashboard_ciclo():
    if not st.session_state.get('ciclo_ativo', False): return
    st.subheader("📊 Dados do Ciclo Atual")
    info = st.session_state.ciclo_info
    inicio_str = info.get('inicio').strftime('%d/%m/%Y') if info.get('inicio') else 'N/D'
    fim_str = info.get('fim').strftime('%d/%m/%Y') if info.get('fim') else 'N/D'
    st.write(f"**Período:** {inicio_str} a {fim_str}")
    total_jogos = len(st.session_state.jogos)
    if total_jogos > 0:
        jogos_concluidos = len(st.session_state.jogos[st.session_state.jogos['Status'] != 'Pendente'])
        percent_concluido = (jogos_concluidos / total_jogos * 100)
    else: jogos_concluidos, percent_concluido = 0, 0
    c1, c2, c3 = st.columns(3)
    c1.metric("Total de Partidas", f"{total_jogos}")
    c2.metric("Partidas Concluídas", f"{jogos_concluidos}")
    c3.metric("Progresso do Ciclo", f"{percent_concluido:.1f}%")
    st.progress(percent_concluido / 100)
    st.divider()

def gerar_tabela_jogos_por_classe(classe):
    jogadores_classe = st.session_state.jogadores[st.session_state.jogadores['Classe'] == classe]['Nome'].tolist()
    if len(jogadores_classe) < 2: return pd.DataFrame()
    confrontos = list(combinations(jogadores_classe, 2))
    jogos_df = pd.DataFrame(confrontos, columns=['Jogador 1', 'Jogador 2'])
    jogos_df['Classe'], jogos_df['Resultado'], jogos_df['Status'], jogos_df['Detalhes'], jogos_df['Data'] = [classe, '-', 'Pendente', '', pd.NaT]
    return jogos_df

def calcular_ranking():
    if st.session_state.jogos.empty or st.session_state.jogadores.empty:
        st.session_state.ranking = pd.DataFrame(); return
    jogos_finalizados = st.session_state.jogos[st.session_state.jogos['Status'].isin(['Finalizado', 'W.O.'])].copy()
    ranking_data = {nome: {'Pontos': 0, 'Jogos': 0, 'Vitorias': 0, 'Derrotas': 0, 'Sets Vencidos': 0, 'Sets Perdidos': 0, 'Classe': st.session_state.jogadores.loc[st.session_state.jogadores['Nome'] == nome, 'Classe'].iloc[0]} for nome in st.session_state.jogadores['Nome']}
    for _, jogo in jogos_finalizados.iterrows():
        j1, j2, res = jogo['Jogador 1'], jogo['Jogador 2'], jogo['Resultado']
        if not isinstance(res, str) or res in ['-', '0x0']: continue
        s1, s2 = map(int, res.split('x'))
        if j1 not in ranking_data or j2 not in ranking_data: continue
        for p in [j1, j2]: ranking_data[p]['Jogos'] += 1
        ranking_data[j1].update({'Sets Vencidos': ranking_data[j1]['Sets Vencidos'] + s1, 'Sets Perdidos': ranking_data[j1]['Sets Perdidos'] + s2})
        ranking_data[j2].update({'Sets Vencidos': ranking_data[j2]['Sets Vencidos'] + s2, 'Sets Perdidos': ranking_data[j2]['Sets Perdidos'] + s1})
        if s1 > s2:
            ranking_data[j1]['Vitorias'] += 1; ranking_data[j2]['Derrotas'] += 1
            ranking_data[j1]['Pontos'] += 3 if s2 == 0 else 2
            if s2 == 1: ranking_data[j2]['Pontos'] += 1
        elif s2 > s1:
            ranking_data[j2]['Vitorias'] += 1; ranking_data[j1]['Derrotas'] += 1
            ranking_data[j2]['Pontos'] += 3 if s1 == 0 else 2
            if s1 == 1: ranking_data[j1]['Pontos'] += 1
    if not ranking_data: st.session_state.ranking = pd.DataFrame(); return
    rdf = pd.DataFrame.from_dict(ranking_data, orient='index')
    rdf['Saldo de Sets'] = rdf['Sets Vencidos'] - rdf['Sets Perdidos']
    rdf = rdf.reset_index().rename(columns={'index': 'Nome'})
    st.session_state.ranking = rdf.sort_values(by=['Classe', 'Pontos', 'Saldo de Sets'], ascending=[True, False, False]).reset_index(drop=True)

def pagina_ranking():
    st.header("🏆 Ranking Atual - Atlântico Tênis Clube")
    exibir_dashboard_ciclo()
    if 'ranking' not in st.session_state or st.session_state.ranking.empty: calcular_ranking()
    if st.session_state.ranking.empty: st.info("O ranking será exibido aqui."); return
    for classe in sorted([c for c in st.session_state.ranking['Classe'].unique() if pd.notna(c)]):
        st.subheader(f"Classe {classe}")
        rc = st.session_state.ranking[st.session_state.ranking['Classe'] == classe].copy()
        rc.insert(0, 'Posição', range(1, len(rc) + 1))
        st.dataframe(rc[['Posição', 'Nome', 'Pontos', 'Jogos', 'Vitorias', 'Derrotas', 'Saldo de Sets']], use_container_width=True, hide_index=True)

def pagina_tabela_de_jogos():
    st.header("📅 Tabela de Jogos")
    editing_index = st.session_state.get('editing_game_index')
    if editing_index is not None:
        st.subheader("✏️ Editando Resultado do Jogo")
        form_registro(None, None, index_jogo_editar=editing_index)
        if st.button("Cancelar Edição"): st.session_state.editing_game_index = None; st.rerun()
        return
    if not st.session_state.ciclo_ativo: st.warning("O ciclo de jogos não está ativo."); return
    if st.session_state.jogos.empty: st.info("Ainda não há jogos neste ciclo."); return
    for classe in sorted(st.session_state.jogos['Classe'].unique()):
        st.subheader(f"Jogos da Classe {classe}")
        jdf = st.session_state.jogos[st.session_state.jogos['Classe'] == classe].copy().sort_values(by="Data", ascending=False)
        st.dataframe(jdf[['Data', 'Jogador 1', 'Jogador 2', 'Resultado', 'Detalhes', 'Status']], hide_index=True, use_container_width=True, column_config={"Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
        with st.expander("Registrar Novo Resultado"):
            jogos_pendentes = jdf[jdf['Status'] == 'Pendente']
            if not jogos_pendentes.empty: form_registro(jogos_pendentes, classe)
            else: st.success("Todos os jogos desta classe foram finalizados!")
        with st.expander("Gerenciar Resultados Lançados"):
            jogos_finalizados = jdf[jdf['Status'] != 'Pendente']
            if not jogos_finalizados.empty:
                opts = jogos_finalizados.apply(lambda x: f"{x['Jogador 1']} vs {x['Jogador 2']}", axis=1)
                jogo_sel = st.selectbox("Selecione um jogo", opts, index=None, key=f"sel_{classe}")
                if jogo_sel:
                    j1, j2 = jogo_sel.split(' vs ')
                    idx = st.session_state.jogos[(st.session_state.jogos['Jogador 1'] == j1) & (st.session_state.jogos['Jogador 2'] == j2) & (st.session_state.jogos['Classe'] == classe)].index[0]
                    c1, c2 = st.columns(2)
                    if c1.button("✏️ Editar", key=f"ed_{idx}"): st.session_state.editing_game_index = idx; st.rerun()
                    if c2.button("🔄 Desfazer", key=f"un_{idx}"):
                        st.session_state.jogos.loc[idx, ['Resultado', 'Status', 'Detalhes', 'Data']] = ['-', 'Pendente', '', pd.NaT]
                        salvar_jogos(); calcular_ranking(); st.success("Lançamento desfeito!"); st.rerun()

def form_registro(jogos_pendentes, classe, index_jogo_editar=None):
    is_edit = index_jogo_editar is not None
    def_scores, def_stb, def_data = [''] * 6, False, datetime.today()
    if is_edit:
        jogo = st.session_state.jogos.loc[index_jogo_editar]
        classe, detalhes, data = jogo['Classe'], jogo['Detalhes'], jogo['Data']
        if pd.notna(data): def_data = data
        if isinstance(detalhes, str) and 'W.O.' not in detalhes and 'Dupla' not in detalhes:
            nums = re.findall(r'\d+', detalhes)
            if len(nums) >= 4: def_scores[:4] = nums[:4]
            if len(nums) == 6: def_scores[4:], def_stb = nums[4:], True
    with st.form(key=f'form_res_{index_jogo_editar or classe}'):
        if is_edit: st.info(f"Editando: **{jogo['Jogador 1']} vs {jogo['Jogador 2']}**")
        else: jogo_sel = st.selectbox("Selecione o Jogo", jogos_pendentes.apply(lambda x: f"{x['Jogador 1']} vs {x['Jogador 2']}", axis=1), index=None)
        data_partida = st.date_input("Data da Partida", value=def_data)
        c1, c2 = st.columns(2)
        s1j1, s1j2 = c1.text_input("Set 1-J1", def_scores[0]), c2.text_input("Set 1-J2", def_scores[1])
        s2j1, s2j2 = c1.text_input("Set 2-J1", def_scores[2]), c2.text_input("Set 2-J2", def_scores[3])
        stb = st.checkbox("3º set (Super Tie-break)?", def_stb)
        s3j1, s3j2 = ('0', '0')
        if stb: s3j1, s3j2 = c1.text_input("STB-J1", def_scores[4]), c2.text_input("STB-J2", def_scores[5])
        if st.form_submit_button("Salvar"):
            try:
                if not all([s1j1, s1j2, s2j1, s2j2]) or (stb and not all([s3j1, s3j2])): st.error("Preencha todos os campos."); return
                scores = list(map(int, [s1j1, s1j2, s2j1, s2j2, s3j1, s3j2]))
                s1, s2 = (scores[0]>scores[1]) + (scores[2]>scores[3]) + (scores[4]>scores[5]), (scores[1]>scores[0]) + (scores[3]>scores[2]) + (scores[5]>scores[4])
                if max(s1, s2) != 2: st.error("Placar inválido."); return
                res, det = f"{s1}x{s2}", f"{scores[0]}x{scores[1]}, {scores[2]}x{scores[3]}"
                if stb: det += f", {scores[4]}x{scores[5]} (STB)"
                idx = index_jogo_editar
                if not is_edit:
                    if not jogo_sel: st.error("Selecione um jogo."); return
                    j1, j2 = jogo_sel.split(' vs '); idx = jogos_pendentes[(jogos_pendentes['Jogador 1']==j1)&(jogos_pendentes['Jogador 2']==j2)].index[0]
                st.session_state.jogos.loc[idx, ['Resultado', 'Detalhes', 'Status', 'Data']] = [res, det, 'Finalizado', data_partida]
                if is_edit: st.session_state.editing_game_index = None
                salvar_jogos(); calcular_ranking(); st.success("Resultado gravado!"); st.rerun()
            except (ValueError, TypeError): st.error("Placar deve conter apenas números.")

def pagina_administracao():
    st.header("⚙️ Painel do Administrador")
    st.subheader("Gestão de Ciclos")
    if not st.session_state.ciclo_ativo:
        with st.form("form_novo_ciclo"):
            c1, c2 = st.columns(2); data_inicio, data_fim = c1.date_input("Início"), c2.date_input("Fim")
            if st.form_submit_button("🚀 Iniciar Novo Ciclo"):
                if len(st.session_state.jogadores) < 2: st.warning("Cadastre pelo menos 2 jogadores."); return
                classes = st.session_state.jogadores['Classe'].dropna().unique()
                if len(classes) == 0: st.error("Nenhum jogador com classe definida."); return
                st.session_state.jogos = pd.concat([gerar_tabela_jogos_por_classe(c) for c in classes], ignore_index=True)
                st.session_state.ciclo_ativo, st.session_state.ciclo_info = True, {"inicio": data_inicio, "fim": data_fim}
                salvar_jogos(); salvar_ciclo_info(); st.rerun()
    if st.button("🏁 Fechar Ciclo", disabled=not st.session_state.ciclo_ativo, type="primary"): st.session_state.show_fechar_ciclo = True
    if st.session_state.get('show_fechar_ciclo'): handle_fechar_ciclo()
    st.divider()
    st.subheader("Gestão de Jogadores")
    jog_edit_df = st.data_editor(st.session_state.jogadores, num_rows="dynamic", use_container_width=True, key="editor_jogadores")
    if st.button("Salvar Jogadores"):
        jog_final = jog_edit_df.dropna(subset=['Nome', 'Classe']); jog_final = jog_final[jog_final['Nome'] != '']
        st.session_state.jogadores = jog_final.reset_index(drop=True); salvar_jogadores(); st.rerun()

def handle_fechar_ciclo():
    jogos_pendentes = st.session_state.jogos[st.session_state.jogos['Status'] == 'Pendente']
    if not jogos_pendentes.empty:
        st.subheader("Resolver Jogos Pendentes");
        for idx, jogo in jogos_pendentes.iterrows():
            j1, j2 = jogo['Jogador 1'], jogo['Jogador 2']
            c = st.columns([3, 1, 1, 1]); c[0].write(f"**{j1} vs {j2}**")
            if c[1].button(f"W.O. {j1}", key=f"wo1_{idx}"): st.session_state.jogos.loc[idx, ['Resultado','Detalhes','Status']] = ['2x0','W.O.','W.O.']; salvar_jogos(); st.rerun()
            if c[2].button(f"W.O. {j2}", key=f"wo2_{idx}"): st.session_state.jogos.loc[idx, ['Resultado','Detalhes','Status']] = ['0x2','W.O.','W.O.']; salvar_jogos(); st.rerun()
            if c[3].button("Derrota Dupla", key=f"dd_{idx}"): st.session_state.jogos.loc[idx, ['Resultado','Detalhes','Status']] = ['0x0','Derrota Dupla','Finalizado']; salvar_jogos(); st.rerun()
    else:
        st.success("Todos os jogos finalizados!")
        if st.button("Confirmar Fechamento do Ciclo"):
            calcular_ranking()
            ranking_final, jog_atualizado = st.session_state.ranking.copy(), st.session_state.jogadores.copy().set_index('Nome')
            classes = sorted([c for c in ranking_final['Classe'].unique() if pd.notna(c)])
            for i, classe in enumerate(classes):
                rc = ranking_final[ranking_final['Classe'] == classe].sort_values(by=['Pontos', 'Saldo de Sets'], ascending=False)
                if i < len(classes) - 1 and len(rc) > 2:
                    for j in rc.tail(2)['Nome'].tolist(): jog_atualizado.loc[j, 'Classe'] = classes[i+1]
                if i > 0 and len(rc) > 2:
                    for j in rc.head(2)['Nome'].tolist(): jog_atualizado.loc[j, 'Classe'] = classes[i-1]
            st.session_state.jogadores = jog_atualizado.reset_index()
            st.session_state.ciclo_ativo, st.session_state.show_fechar_ciclo = False, False
            st.session_state.jogos = st.session_state.jogos.iloc[0:0]
            salvar_jogadores(); salvar_jogos(); salvar_ciclo_info(); st.rerun()

def main():
    # A criação das tabelas no Supabase é feita pelo script SQL, não mais aqui.
    inicializar_session_state() 
    st.sidebar.title("🎾 Menu de Navegação")
    status_ciclo = 'Ativo' if st.session_state.ciclo_ativo else 'Inativo'
    st.sidebar.info(f"Ciclo Atual: **{status_ciclo}**")
    paginas = {"Ranking": pagina_ranking, "Tabela de Jogos": pagina_tabela_de_jogos, "Administração": pagina_administracao}
    selecao = st.sidebar.radio("Escolha uma página", list(paginas.keys()))
    paginas[selecao]()

if __name__ == "__main__":
    main()
