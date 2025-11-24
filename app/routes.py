from flask import Blueprint, render_template, redirect, url_for, request, session, flash, send_file, Response, current_app
from . import db
from .models import Termometro, Verificacao, Usuario
from .forms import TermometroForm, VerificacaoForm, LoginForm, UsuarioForm
from functools import wraps
import pandas as pd
import io
import statistics
# from weasyprint import HTML  # (mantido comentado; importe se for usar PDF aqui)
from datetime import datetime, date, time, timedelta
from collections import defaultdict
from sqlalchemy import func
import pytz
from pathlib import Path
import qrcode


bp = Blueprint('main', __name__)

# =========================
# Decorators
# =========================
def login_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Você precisa estar logado para acessar esta página.', 'warning')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_requerido(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Acesso restrito a administradores.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


# =========================
# Rotas
# =========================
@bp.route('/')
def index():
    termo_busca = request.args.get('q', '').strip()
    setor_filtro = request.args.get('setor')

    query = Termometro.query

    if setor_filtro:
        query = query.filter_by(setor=setor_filtro)

    if termo_busca:
        termo_like = f"%{termo_busca}%"
        query = query.filter(
            (Termometro.identificacao.ilike(termo_like)) |
            (Termometro.equipamento.ilike(termo_like))
        )

    termometros = query.all()

    setores = db.session.query(Termometro.setor).distinct().all()
    setores = [s[0] for s in setores]

    # Recalcular alertas do dia (fuso de SP)
    sp_tz = pytz.timezone('America/Sao_Paulo')
    hoje_sp = datetime.now(sp_tz).date()
    inicio_local = sp_tz.localize(datetime.combine(hoje_sp, time.min))
    inicio_utc = inicio_local.astimezone(pytz.utc)
    fim_utc = (inicio_local + timedelta(days=1)).astimezone(pytz.utc)

    verificacoes_hoje = Verificacao.query.filter(
        Verificacao.data_hora >= inicio_utc,
        Verificacao.data_hora < fim_utc
    ).all()

    verificacoes_por_termometro = {v.termometro_id: v for v in verificacoes_hoje}

    termometros_atrasados = []
    termometros_incompletos = []

    for termo in termometros:
        v = verificacoes_por_termometro.get(termo.id)
        if not v:
            termometros_atrasados.append(termo.id)
        elif v.temperatura_max is None or v.temperatura_min is None:
            termometros_incompletos.append(termo.id)

    return render_template(
        'index.html',
        termometros=termometros,
        setores=setores,
        setor_filtro=setor_filtro,
        termo_busca=termo_busca,
        termometros_atrasados=termometros_atrasados,
        termometros_incompletos=termometros_incompletos
    )


@bp.route('/cadastrar', methods=['GET', 'POST'])
@login_requerido
def cadastrar():
    form = TermometroForm()
    if form.validate_on_submit():
        termometro = Termometro(
            setor=form.setor.data,
            equipamento=form.equipamento.data,
            especificacao=form.especificacao.data,
            identificacao=form.identificacao.data,
            padrao_identificacao=form.padrao_identificacao.data
        )
        db.session.add(termometro)
        db.session.commit()

        # ✅ GERAÇÃO AUTOMÁTICA DO QR CODE (salvando dentro do projeto)
        url = url_for('main.verificar', id=termometro.id, _external=True)
        img = qrcode.make(url)

        # Ex: .../app/static/qrcodes/
        qr_dir = Path(current_app.root_path) / "static" / "qrcodes"
        qr_dir.mkdir(parents=True, exist_ok=True)

        qr_path = qr_dir / f"{termometro.identificacao}.png"
        img.save(qr_path)

        flash('Termômetro cadastrado e QR Code gerado com sucesso!', 'success')
        return redirect(url_for('main.index'))

    return render_template('cadastrar_termometro.html', form=form)


@bp.route('/historico/<int:id>')
@login_requerido
def historico(id):
    termometro = Termometro.query.get_or_404(id)
    verificacoes = Verificacao.query.filter_by(termometro_id=termometro.id).all()

    # 1. Agrupa por mês/ano inicialmente
    # O defaultdict cria uma lista automaticamente para cada chave nova
    agrupado_temp = defaultdict(list)
    for v in verificacoes:
        # Garante que usamos a data correta (SP)
        data_sp = v.get_data_hora_sp()
        mes_ano = data_sp.strftime('%m/%Y')
        agrupado_temp[mes_ano].append(v)

    # 2. Processa cada mês para calcular estatísticas e ordenar
    historico_mensal = {}

    # Iteramos sobre o dicionário temporário
    for mes, lista_verificacoes in agrupado_temp.items():
        
        # Ordena a lista de verificações por data/hora (da mais antiga para a mais nova)
        lista_ordenada = sorted(lista_verificacoes, key=lambda v: v.get_data_hora_sp())

        # Extrai apenas os valores de temperatura válidos (ignora None) para cálculo
        valores_mes = [v.temperatura_atual for v in lista_ordenada if v.temperatura_atual is not None]

        # === CÁLCULO ESTATÍSTICO (Igual ao Excel) ===
        if valores_mes:
            media_mes = statistics.mean(valores_mes)
            # Desvio padrão requer pelo menos 2 pontos de dados
            if len(valores_mes) > 1:
                desvio_mes = statistics.stdev(valores_mes)
            else:
                desvio_mes = 0.0
        else:
            media_mes = 0.0
            desvio_mes = 0.0

        # 3. Monta a estrutura final que o template espera
        # Agora 'historico_mensal[mes]' não é mais só uma lista, é um objeto com tudo que precisamos
        historico_mensal[mes] = {
            'lista': lista_ordenada,  # A lista de objetos Verificacao
            'media': media_mes,       # A média calculada
            'desvio': desvio_mes      # O desvio padrão calculado
        }

    # Opcional: Ordenar os meses (chaves) se quiser que apareçam em ordem cronológica ou inversa na tela
    # Aqui estamos mantendo a ordem de inserção ou aleatória do dict, mas o template itera sobre ele.

    return render_template(
        'historico.html',
        termometro=termometro,
        historico_mensal=historico_mensal
    )


@bp.route('/exportar_excel/<int:id>')
@login_requerido
def exportar_excel(id):
    termometro = Termometro.query.get_or_404(id)

    data = []
    for v in termometro.verificacoes:
        data.append({
            'Data': v.get_data_hora_sp().strftime('%d/%m/%Y'),
            'Hora': v.get_data_hora_sp().strftime('%H:%M'),
            'Responsável': v.responsavel,
            'Temperatura Atual (ºC)': v.temperatura_atual,
            'Temperatura Máxima (ºC)': v.temperatura_max,
            'Temperatura Mínima (ºC)': v.temperatura_min,
            'Observação': v.observacao
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Verificações')

    output.seek(0)
    return send_file(output, download_name='controle_temperatura.xlsx', as_attachment=True)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'usuario_id' in session:
        return redirect(url_for('main.index'))

    form = LoginForm()
    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(username=form.username.data).first()
        if usuario and usuario.check_senha(form.senha.data):
            session['usuario_id'] = usuario.id
            session['usuario_nome'] = usuario.username
            session['is_admin'] = usuario.is_admin
            flash('Login efetuado com sucesso.', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Usuário ou senha incorretos.', 'danger')

    return render_template('login.html', form=form)


@bp.route('/logout')
@login_requerido
def logout():
    session.clear()
    flash('Você saiu da sessão.', 'info')
    return redirect(url_for('main.login'))


@bp.route('/excluir-verificacao/<int:id>', methods=['POST'])
@admin_requerido
def excluir_verificacao(id):
    verificacao = Verificacao.query.get_or_404(id)
    db.session.delete(verificacao)
    db.session.commit()
    flash('Verificação excluída com sucesso!', 'success')
    return redirect(request.referrer or url_for('main.index'))


@bp.route('/verificacao/<int:id>/editar', methods=['GET', 'POST'])
@admin_requerido
def editar_verificacao(id):
    verificacao = Verificacao.query.get_or_404(id)
    form = VerificacaoForm(obj=verificacao)

    if form.validate_on_submit():
        verificacao.temperatura_atual = form.temperatura_atual.data
        verificacao.temperatura_max = form.temperatura_max.data
        verificacao.temperatura_min = form.temperatura_min.data
        verificacao.responsavel = form.responsavel.data
        verificacao.observacao = form.observacao.data
        db.session.commit()
        flash('Verificação atualizada com sucesso!', 'success')
        return redirect(url_for('main.historico', id=verificacao.termometro_id))

    return render_template('editar_verificacao.html', form=form)


@bp.route('/cadastrar_usuario', methods=['GET', 'POST'])
@admin_requerido
def cadastrar_usuario():
    form = UsuarioForm()
    if form.validate_on_submit():
        novo_usuario = Usuario(
            username=form.username.data,
            is_admin=form.is_admin.data
        )
        # sempre gere o hash pela função
        novo_usuario.set_senha(form.senha.data)
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Usuário cadastrado com sucesso!', 'success')
        return redirect(url_for('main.index'))
    return render_template('cadastrar_usuario.html', form=form)


@bp.route('/excluir-termometro/<int:id>', methods=['POST'])
@admin_requerido
def excluir_termometro(id):
    termometro = Termometro.query.get_or_404(id)

    # Apaga as verificações ligadas ao termômetro
    for verificacao in termometro.verificacoes:
        db.session.delete(verificacao)

    db.session.delete(termometro)
    db.session.commit()
    flash('Termômetro excluído com sucesso!', 'success')
    return redirect(url_for('main.index'))


from wtforms.validators import DataRequired

@bp.route('/verificar/<int:id>', methods=['GET', 'POST'])
@login_requerido
def verificar(id):
    termometro = Termometro.query.get_or_404(id)
    form = VerificacaoForm()

    # Pré-popula o responsável para usuários comuns
    if not session.get('is_admin'):
        form.responsavel.data = session.get('usuario_nome')

    # Timezone SP e intervalo do dia
    sp_tz = pytz.timezone('America/Sao_Paulo')
    hoje_sp = datetime.now(sp_tz).date()
    inicio_local = sp_tz.localize(datetime.combine(hoje_sp, time.min))
    inicio_utc = inicio_local.astimezone(pytz.utc)
    fim_utc = (inicio_local + timedelta(days=1)).astimezone(pytz.utc)

    # Verifica se já existe verificação hoje
    primeira = Verificacao.query.filter(
        Verificacao.termometro_id == id,
        Verificacao.data_hora >= inicio_utc,
        Verificacao.data_hora < fim_utc
    ).order_by(Verificacao.data_hora).first()

    exigir_maxmin = bool(primeira)

    # Pré-preenche temperatura/observação caso atualizando a segunda leitura
    if request.method == 'GET' and exigir_maxmin and primeira:
        form.temperatura_atual.data = primeira.temperatura_atual
        form.observacao.data = primeira.observacao
        form.observacao_personalizada.data = (
            primeira.observacao if primeira.observacao not in dict(form.observacao.choices).keys() else ""
        )

    # Primeira leitura do dia (cria registro)
    if request.method == 'POST' and not exigir_maxmin:
        atual = form.temperatura_atual.data
        max_temp = form.temperatura_max.data
        min_temp = form.temperatura_min.data

        if atual is None:
            flash('Preencha a temperatura atual.', 'danger')
        else:
            observacao_final = form.observacao.data
            if observacao_final == "I" and form.observacao_personalizada.data:
                observacao_final = form.observacao_personalizada.data

            v = Verificacao(
                temperatura_atual=atual,
                temperatura_max=max_temp,
                temperatura_min=min_temp,
                responsavel=form.responsavel.data,
                observacao=observacao_final,
                data_hora=form.data_manual.data.astimezone(pytz.utc) if form.data_manual.data else datetime.now(pytz.utc),
                termometro_id=id
            )
            db.session.add(v)
            db.session.commit()
            flash('Leitura registrada com sucesso!', 'success')
            return redirect(url_for('main.historico', id=id))

    # Segunda leitura do dia (atualiza registro com máx/mín)
    if form.validate_on_submit() and exigir_maxmin and primeira:
        observacao_final = form.observacao.data
        if observacao_final == "I" and form.observacao_personalizada.data:
            observacao_final = form.observacao_personalizada.data

        primeira.temperatura_max = form.temperatura_max.data
        primeira.temperatura_min = form.temperatura_min.data
        primeira.observacao = observacao_final
        db.session.commit()
        flash('Leitura final do dia atualizada com Máx/Mín.', 'success')
        return redirect(url_for('main.historico', id=id))

    # Em caso de erro no POST final
    if request.method == 'POST' and exigir_maxmin and form.errors:
        flash(f'Erros no formulário: {form.errors}', 'danger')

    return render_template(
        'verificar_temperatura.html',
        form=form,
        termometro=termometro,
        exigir_maxmin=exigir_maxmin
    )


@bp.route('/listar_admins')
def listar_admins():
    admins = Usuario.query.filter_by(is_admin=True).all()
    return '<br>'.join([f"Admin: {admin.username}" for admin in admins])


@bp.route('/editar-termometro/<int:id>', methods=['GET', 'POST'])
@admin_requerido
def editar_termometro(id):
    termometro = Termometro.query.get_or_404(id)
    form = TermometroForm(obj=termometro)

    if form.validate_on_submit():
        termometro.setor = form.setor.data
        termometro.equipamento = form.equipamento.data
        termometro.especificacao = form.especificacao.data
        termometro.identificacao = form.identificacao.data
        termometro.padrao_identificacao = form.padrao_identificacao.data
        db.session.commit()
        flash('Termômetro atualizado com sucesso!', 'success')
        return redirect(url_for('main.index'))

    return render_template('cadastrar_termometro.html', form=form, editar=True)


@bp.route('/exportar_planilha_geral')
@admin_requerido
def exportar_planilha_geral():
    termometros = Termometro.query.all()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for termometro in termometros:
            dados = []
            for v in termometro.verificacoes:
                dados.append({
                    'Data': v.get_data_hora_sp().strftime('%d/%m/%Y'),
                    'Hora': v.get_data_hora_sp().strftime('%H:%M'),
                    'Responsável': v.responsavel,
                    'T Atual (°C)': v.temperatura_atual,
                    'T Máx (°C)': v.temperatura_max,
                    'T Mín (°C)': v.temperatura_min,
                    'Observação': v.observacao
                })

            df = pd.DataFrame(dados)
            aba = termometro.identificacao or f"Termometro_{termometro.id}"
            df.to_excel(writer, sheet_name=aba[:31], index=False)  # Excel limita o nome da aba a 31 chars

    output.seek(0)
    return send_file(output, download_name='dados_termometros.xlsx', as_attachment=True)


@bp.route('/qr/<int:id>')
@login_requerido
def gerar_qr(id):
    url = url_for('main.verificar', id=id, _external=True)
    img = qrcode.make(url)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return send_file(buffer, mimetype='image/png', download_name=f'termometro_{id}_qr.png')

@bp.route('/dados_carta_controle/<int:id>/<string:mes_ano_str>') # Recebe o mês também para filtrar
@login_requerido
def dados_carta_controle(id, mes_ano_str):
    # Exemplo de mes_ano_str: "08-2025" (precisa adaptar no frontend para enviar isso)
    # Ou simplifique pegando os ultimos 30 registros se preferir.
    
    termometro = Termometro.query.get_or_404(id)
    
    # Aqui você deve filtrar as verificações do mês específico
    # (Simplificando pegando todas para o exemplo, mas o ideal é filtrar por data)
    verificacoes = Verificacao.query.filter_by(termometro_id=id).order_by(Verificacao.data_hora.asc()).all()
    
    # Extrai os valores (ignora onde não tem temperatura)
    valores = [v.temperatura_atual for v in verificacoes if v.temperatura_atual is not None]
    datas = [v.get_data_hora_sp().strftime('%d/%m') for v in verificacoes if v.temperatura_atual is not None]

    # === O CÉREBRO MATEMÁTICO (Igual sua planilha) ===
    if len(valores) > 1:
        media = statistics.mean(valores)       # Calcula a Média (X barra)
        desvio = statistics.stdev(valores)     # Calcula o Desvio Padrão (Sigma)
    else:
        # Se tiver menos de 2 dados, não dá pra calcular desvio
        media = valores[0] if valores else 0
        desvio = 0

    # Calcula as linhas da Carta Controle
    s3_sup = media + (3 * desvio)  # NC Superior (+3S) Linha Vermelha
    s2_sup = media + (2 * desvio)  # NA Superior (+2S) Linha Amarela
    s1_sup = media + (1 * desvio)  # (+1S) Linha Verde
    
    s1_inf = media - (1 * desvio)  # (-1S) Linha Verde
    s2_inf = media - (2 * desvio)  # NA Inferior (-2S) Linha Amarela
    s3_inf = media - (3 * desvio)  # NC Inferior (-3S) Linha Vermelha

    # Prepara o JSON para o Gráfico
    # Criamos listas repetindo o mesmo valor para formar linhas retas no gráfico
    qtd = len(datas)
    
    return {
        'labels': datas,
        'datasets': [
            {
                'label': 'Resultado (°C)',
                'data': valores,
                'borderColor': 'black',
                'borderWidth': 2,
                'pointBackgroundColor': 'blue',
                'tension': 0 # Linha reta entre pontos
            },
            # Linhas de Controle (Vermelhas)
            {'label': '+3S (NC)', 'data': [s3_sup]*qtd, 'borderColor': 'red', 'borderWidth': 1, 'pointRadius': 0},
            {'label': '-3S (NC)', 'data': [s3_inf]*qtd, 'borderColor': 'red', 'borderWidth': 1, 'pointRadius': 0},
            
            # Linhas de Alerta (Amarelas)
            {'label': '+2S (NA)', 'data': [s2_sup]*qtd, 'borderColor': '#FFD700', 'borderWidth': 1, 'pointRadius': 0, 'borderDash': [5,5]},
            {'label': '-2S (NA)', 'data': [s2_inf]*qtd, 'borderColor': '#FFD700', 'borderWidth': 1, 'pointRadius': 0, 'borderDash': [5,5]},
            
            # Linhas de 1 Sigma (Verdes)
            {'label': '+1S', 'data': [s1_sup]*qtd, 'borderColor': 'green', 'borderWidth': 0.5, 'pointRadius': 0},
            {'label': '-1S', 'data': [s1_inf]*qtd, 'borderColor': 'green', 'borderWidth': 0.5, 'pointRadius': 0},
            
            # Média (Laranja)
            {'label': 'Média', 'data': [media]*qtd, 'borderColor': 'orange', 'borderWidth': 2, 'pointRadius': 0, 'borderDash': [2,2]}
        ],
        # Enviamos os valores calculados também para preencher a tabela se quiser
        'estatisticas': {
            'media': round(media, 2),
            'desvio': round(desvio, 4),
            'nc_sup': round(s3_sup, 2),
            'nc_inf': round(s3_inf, 2)
        }
    }
