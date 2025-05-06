from flask import Blueprint, render_template, redirect, url_for, request, session, flash, send_file, Response
from . import db
from .models import Termometro, Verificacao, Usuario
from .forms import TermometroForm, VerificacaoForm, LoginForm, UsuarioForm
from functools import wraps
import pandas as pd
import io
from weasyprint import HTML
from datetime import datetime

bp = Blueprint('main', __name__)

# Decorators
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

# Rotas
@bp.route('/')
def index():
    setor_filtro = request.args.get('setor')
    if setor_filtro:
        termometros = Termometro.query.filter_by(setor=setor_filtro).all()
    else:
        termometros = Termometro.query.all()

    setores = db.session.query(Termometro.setor).distinct().all()
    setores = [s[0] for s in setores]  # extrai o nome do setor

    return render_template('index.html', termometros=termometros, setores=setores, setor_filtro=setor_filtro)

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
        return redirect(url_for('main.index'))
    return render_template('cadastrar_termometro.html', form=form)



@bp.route('/historico/<int:id>')
@login_requerido
def historico(id):
    termometro = Termometro.query.get_or_404(id)
    verificacoes = Verificacao.query.filter_by(termometro_id=termometro.id).all()
    return render_template('historico.html', termometro=termometro, verificacoes=verificacoes)

@bp.route('/historico/<int:id>/pdf')
@login_requerido
def historico_pdf(id):
    termometro = Termometro.query.get_or_404(id)
    data_atual = datetime.now()
    mes = data_atual.strftime("%m")
    ano = data_atual.strftime("%Y")
    
    html_content = render_template('historico.html', termometro=termometro, mes=mes, ano=ano)
    pdf = HTML(string=html_content).write_pdf()
    
    response = Response(pdf, mimetype='application/pdf')
    response.headers['Content-Disposition'] = f'inline; filename=historico_{termometro.id}.pdf'
    
    return response

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
            senha_hash=form.senha.data,  # Corrija para usar hash
            is_admin=form.is_admin.data
        )
        novo_usuario.set_senha(form.senha.data)  # Usa a função para hash de senha
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Usuário cadastrado com sucesso!', 'success')
        return redirect(url_for('main.index'))
    return render_template('cadastrar_usuario.html', form=form)

@bp.route('/excluir-termometro/<int:id>', methods=['POST'])
@admin_requerido
def excluir_termometro(id):
    termometro = Termometro.query.get_or_404(id)

    # Também apagar todas as verificações ligadas ao termômetro antes de apagar o termômetro
    for verificacao in termometro.verificacoes:
        db.session.delete(verificacao)

    db.session.delete(termometro)
    db.session.commit()
    flash('Termômetro excluído com sucesso!', 'success')
    return redirect(url_for('main.index'))


from datetime import datetime
import pytz  # Certifique-se que está no topo do arquivo

@bp.route('/verificar/<int:id>', methods=['GET', 'POST'])
@login_requerido
def verificar(id):
    termometro = Termometro.query.get_or_404(id)
    form = VerificacaoForm()

    # Preenche o campo responsável automaticamente se não for admin
    if not session.get('is_admin'):
        form.responsavel.data = session.get('usuario_nome')

    # Mostra erro caso o form não seja válido (ajuda na depuração)
    if request.method == 'POST' and not form.validate():
        flash('Erro ao registrar verificação. Verifique os campos.', 'danger')

    if form.validate_on_submit():
        # Admin pode escolher data/hora manual
        if session.get('is_admin'):
            data_hora_str = request.form.get('data_hora')
            if data_hora_str:
                # Trata a hora como sendo de São Paulo e converte para UTC
                sp_tz = pytz.timezone('America/Sao_Paulo')
                local_dt = sp_tz.localize(datetime.strptime(data_hora_str, "%Y-%m-%dT%H:%M"))
                data_hora = local_dt.astimezone(pytz.utc)
            else:
                data_hora = datetime.now(pytz.utc)
            responsavel = form.responsavel.data
        else:
            # Para usuário comum: usa hora atual em UTC e nome da sessão
            data_hora = datetime.now(pytz.utc)
            responsavel = session.get('usuario_nome')

        # Cria nova verificação
        verificacao = Verificacao(
            temperatura_atual=form.temperatura_atual.data,
            temperatura_max=form.temperatura_max.data,
            temperatura_min=form.temperatura_min.data,
            responsavel=responsavel,
            observacao=form.observacao.data,
            data_hora=data_hora,
            termometro_id=termometro.id
        )

        db.session.add(verificacao)
        db.session.commit()

        flash('Verificação registrada com sucesso!', 'success')
        return redirect(url_for('main.historico', id=id))

    return render_template('verificar_temperatura.html', form=form, termometro=termometro)


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
            df.to_excel(writer, sheet_name=aba[:31], index=False)  # Excel limita nome da aba a 31 caracteres

    output.seek(0)
    return send_file(output, download_name='dados_termometros.xlsx', as_attachment=True)

import qrcode

@bp.route('/qr/<int:id>')
@login_requerido
def gerar_qr(id):
    url = url_for('main.verificar', id=id, _external=True)
    img = qrcode.make(url)

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)

    return send_file(buffer, mimetype='image/png', download_name=f'termometro_{id}_qr.png')

