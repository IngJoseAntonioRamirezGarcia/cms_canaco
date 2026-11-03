from django.shortcuts import render, redirect
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from .models import (
    Archivo,
    Perfil,
    Categoria,
    Comentario,
    Publicacion,
    GaleriaPublicacion
)
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.db.models import F

def es_operador(user):
    return user.is_authenticated and user.is_staff and user.is_active


operador_required = user_passes_test(
    es_operador,
    login_url='home:login'
)

def guardar_archivo(upload, user):
    filename = default_storage.save(f"uploads/{upload.name}", upload)

    return Archivo.objects.create(
        nombre=upload.name,
        nombre_temporal=filename,
        ruta=filename,
        tipo=upload.content_type or '',
        tamano=upload.size,
        fk_user=user,
    )

# Create your views here.

def index(request):
    publicaciones = Publicacion.objects.filter(
        estado='publicado'
    ).select_related(
        'categoria',
        'autor',
        'imagen_portada'
    ).order_by('-createdat')

    return render(request, 'home/index.html', {
        'slider': publicaciones[:3],
        'publicaciones': publicaciones[:3],
    })

def base(request):
    return render(request, 'home/base.html')

def categoria(request, pk=None):
    categorias = Categoria.objects.all().order_by('nombre')

    categoria_actual = (
        get_object_or_404(Categoria, pk=pk)
        if pk else None
    )

    publicaciones = Publicacion.objects.filter(
        estado='publicado'
    ).select_related(
        'categoria',
        'autor',
        'imagen_portada'
    )

    if categoria_actual:
        publicaciones = publicaciones.filter(
            categoria=categoria_actual
        )

    return render(request, 'home/categoria.html', {
        'categorias': categorias,
        'categoria_actual': categoria_actual,
        'publicaciones': publicaciones.order_by('-createdat'),
    })

def contactanos(request):
    return render(request, 'home/contactanos.html')


@operador_required
def crear_usuario(request):

    if request.method == 'POST':

        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        apellido_paterno = request.POST.get('apellido_paterno', '').strip()
        apellido_materno = request.POST.get('apellido_materno', '').strip()
        rol = request.POST.get('rol', 'colaborador')
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        # Comprobar campos obligatorios
        if not username or not email or not password1 or not password2:
            messages.error(request, 'Completa todos los campos obligatorios.')
            return redirect('home:crear_usuario')

        # Comprobar contraseñas
        if password1 != password2:
            messages.error(request, 'Las contraseñas no coinciden.')
            return redirect('home:crear_usuario')

        # Validar nombre de usuario
        if User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya existe.')
            return redirect('home:crear_usuario')

        # Validar correo
        if User.objects.filter(email=email).exists():
            messages.error(request, 'El correo electrónico ya está registrado.')
            return redirect('home:crear_usuario')

        # Validar rol
        if rol not in ('colaborador', 'editor', 'administrador'):
            messages.error(request, 'El rol seleccionado no es válido.')
            return redirect('home:crear_usuario')

        # Solo un superusuario puede asignar roles administrativos
        if rol in ('editor', 'administrador') and not request.user.is_superuser:
            messages.error(
                request,
                'No tienes permiso para asignar ese rol.'
            )
            return redirect('home:crear_usuario')

        # Validar seguridad de contraseña
        try:
            validate_password(password1)
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
            return redirect('home:crear_usuario')

        # Crear usuario en auth_user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1,
            first_name=first_name,
            last_name=' '.join(
                filter(None, [apellido_paterno, apellido_materno])
            )
        )

        # Asignar rol
        user.is_staff = rol in ('editor', 'administrador')
        user.is_superuser = rol == 'administrador'
        user.save()

        # Guardar apellidos en el perfil
        perfil, _ = Perfil.objects.get_or_create(user=user)

        perfil.apellido_paterno = apellido_paterno
        perfil.apellido_materno = apellido_materno
        perfil.save()

        messages.success(
            request,
            'Usuario creado correctamente.'
        )

        return redirect('home:crud_usuarios')

    return render(request, 'home/crear_usuario.html')


@operador_required
def crear_publicacion(request):
    categorias = Categoria.objects.all().order_by('nombre')

    if request.method == 'POST':
        publicacion = Publicacion.objects.create(
            titulo=request.POST.get('titulo', '').strip(),
            resumen=request.POST.get('resumen', '').strip(),
            contenido=request.POST.get('contenido', '').strip(),
            categoria_id=request.POST.get('categoria') or None,
            estado=request.POST.get('estado') or 'borrador',
            autor=request.user,
        )

        portada = request.FILES.get('imagen_portada')

        if portada:
            publicacion.imagen_portada = guardar_archivo(
                portada,
                request.user
            )
            publicacion.save()

        for imagen in request.FILES.getlist('galeria'):
            GaleriaPublicacion.objects.create(
                publicacion=publicacion,
                archivo=guardar_archivo(imagen, request.user)
            )

        messages.success(
            request,
            'Publicación creada correctamente.'
        )

        return redirect('home:crud_noticias')

    return render(
        request,
        'home/crear_publicacion.html',
        {'categorias': categorias}
    )


@login_required
def crud_cambiar_contrasena(request):

    if request.method == 'POST':

        actual = request.POST.get('actual', '')
        nueva = request.POST.get('nueva', '')
        confirmar = request.POST.get('confirmar', '')

        user = request.user

        # Comprobar que todos los campos estén completos
        if not actual or not nueva or not confirmar:
            messages.error(request, 'Debes completar todos los campos.')
            return redirect('home:crud_cambiar_contrasena')

        # Verificar la contraseña actual
        if not user.check_password(actual):
            messages.error(request, 'La contraseña actual es incorrecta.')
            return redirect('home:crud_cambiar_contrasena')

        # Verificar que las nuevas contraseñas coincidan
        if nueva != confirmar:
            messages.error(request, 'Las nuevas contraseñas no coinciden.')
            return redirect('home:crud_cambiar_contrasena')

        # Validar la seguridad de la contraseña nueva
        try:
            validate_password(nueva, user=user)
        except ValidationError as error:
            for mensaje in error.messages:
                messages.error(request, mensaje)
            return redirect('home:crud_cambiar_contrasena')

        # Actualizar la contraseña
        user.set_password(nueva)
        user.save()

        # Mantener la sesión iniciada
        update_session_auth_hash(request, user)

        messages.success(
            request,
            'Contraseña actualizada correctamente.'
        )

        return redirect('home:crud_cambiar_contrasena')

    return render(
        request,
        'home/crud_cambiar_contrasena.html'
    )


@operador_required
def crud_categoria(request):

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()

        if nombre:
            Categoria.objects.create(
                nombre=nombre,
                fk_user=request.user
            )

            messages.success(
                request,
                'Categoría agregada correctamente.'
            )

            return redirect('home:crud_categoria')

        messages.error(
            request,
            'Debes escribir el nombre de la categoría.'
        )

    categorias = Categoria.objects.all().order_by('-createdat')

    return render(
        request,
        'home/crud_categorias.html',
        {'categorias': categorias}
    )

@operador_required
def crud_comentarios(request):
    comentarios = Comentario.objects.select_related(
        'publicacion',
        'user'
    ).order_by('-createdat')

    return render(
        request,
        'home/crud_comentarios.html',
        {'comentarios': comentarios}
    )


# APROBAR COMENTARIO
@operador_required
@require_POST
def aprobar_comentario(request, pk):
    comentario = get_object_or_404(Comentario, pk=pk)
    comentario.estado = 'aprobado'
    comentario.save(update_fields=['estado'])

    messages.success(request, 'Comentario aprobado correctamente.')

    return redirect('home:crud_comentarios')


# BLOQUEAR COMENTARIO
@operador_required
@require_POST
def bloquear_comentario(request, pk):
    comentario = get_object_or_404(Comentario, pk=pk)
    comentario.estado = 'bloqueado'
    comentario.save(update_fields=['estado'])

    messages.success(request, 'Comentario bloqueado correctamente.')

    return redirect('home:crud_comentarios')


# ELIMINAR COMENTARIO
@operador_required
@require_POST
def eliminar_comentario(request, pk):
    comentario = get_object_or_404(Comentario, pk=pk)
    comentario.delete()

    messages.success(request, 'Comentario eliminado correctamente.')

    return redirect('home:crud_comentarios')

@operador_required
def crud_noticias(request):
    publicaciones = Publicacion.objects.select_related(
        'categoria',
        'autor'
    ).order_by('-createdat')

    return render(
        request,
        'home/crud_noticias.html',
        {'publicaciones': publicaciones}
    )

@operador_required
def editar_publicacion(request, pk):

    publicacion = get_object_or_404(Publicacion, pk=pk)
    categorias = Categoria.objects.all().order_by('nombre')

    if request.method == 'POST':

        publicacion.titulo = request.POST.get('titulo', '').strip()
        publicacion.resumen = request.POST.get('resumen', '').strip()
        publicacion.contenido = request.POST.get('contenido', '').strip()
        publicacion.categoria_id = request.POST.get('categoria') or None
        publicacion.estado = request.POST.get('estado') or 'borrador'

        portada = request.FILES.get('imagen_portada')

        if portada:
            publicacion.imagen_portada = guardar_archivo(
                portada,
                request.user
            )

        publicacion.save()

        for imagen in request.FILES.getlist('galeria'):
            GaleriaPublicacion.objects.create(
                publicacion=publicacion,
                archivo=guardar_archivo(imagen, request.user)
            )

        messages.success(
            request,
            'Publicación actualizada correctamente.'
        )

        return redirect('home:crud_noticias')

    return render(
        request,
        'home/crear_publicacion.html',
        {
            'categorias': categorias,
            'publicacion': publicacion,
        }
    )

@operador_required
def publicar_publicacion(request, pk):

    publicacion = get_object_or_404(Publicacion, pk=pk)

    publicacion.estado = (
        'publicado'
        if publicacion.estado != 'publicado'
        else 'borrador'
    )

    publicacion.save()

    return redirect('home:crud_noticias')

@operador_required
def eliminar_publicacion(request, pk):

    publicacion = get_object_or_404(Publicacion, pk=pk)

    if request.method == 'POST':
        publicacion.delete()

        messages.success(
            request,
            'Publicación eliminada correctamente.'
        )

    return redirect('home:crud_noticias')

@login_required
def crud_perfil(request):
    user = request.user
    perfil, _ = Perfil.objects.get_or_create(user=user)

    if request.method == 'POST':

        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        apellido_paterno = request.POST.get('apellido_paterno', '').strip()
        apellido_materno = request.POST.get('apellido_materno', '').strip()
        foto = request.FILES.get('foto')

        if not username:
            messages.error(request, 'El nombre de usuario es obligatorio.')
            return redirect('home:crud_perfil')

        if User.objects.filter(username=username).exclude(pk=user.pk).exists():
            messages.error(request, 'Ese nombre de usuario ya está en uso.')
            return redirect('home:crud_perfil')

        if email and User.objects.filter(email=email).exclude(pk=user.pk).exists():
            messages.error(request, 'Ese correo electrónico ya está registrado.')
            return redirect('home:crud_perfil')

        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = ' '.join(
            filter(None, [apellido_paterno, apellido_materno])
        )
        user.save()

        perfil.apellido_paterno = apellido_paterno
        perfil.apellido_materno = apellido_materno

        if foto:
            if foto.content_type not in ('image/jpeg', 'image/png', 'image/webp'):
                messages.error(request, 'Selecciona una imagen JPG, PNG o WebP.')
                return redirect('home:crud_perfil')

            if foto.size > 5 * 1024 * 1024:
                messages.error(request, 'La fotografía no debe superar 5 MB.')
                return redirect('home:crud_perfil')

            perfil.foto_perfil = guardar_archivo(foto, user)

        perfil.save()

        messages.success(request, 'Perfil actualizado correctamente.')
        return redirect('home:perfil')

    return render(
        request,
        'home/crud_perfil.html',
        {'perfil_usuario': perfil}
    )


@operador_required
def crud_usuarios(request):

    for usuario in User.objects.all():
        Perfil.objects.get_or_create(user=usuario)

    usuarios = User.objects.select_related('perfil').order_by('date_joined')

    return render(
        request,
        'home/crud_usuarios.html',
        {'usuarios': usuarios}
    )

@operador_required
def editar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', '').strip()

        if not nombre:
            messages.error(request, 'El nombre es obligatorio.')
            return redirect('home:editar_categoria', pk=pk)

        categoria.nombre = nombre
        categoria.save()

        messages.success(
            request,
            'Categoría actualizada correctamente.'
        )
        return redirect('home:crud_categoria')

    return render(
        request,
        'home/editar_categoria.html',
        {'categoria': categoria}
    )
@operador_required
@require_POST
def eliminar_categoria(request, pk):
    categoria = get_object_or_404(Categoria, pk=pk)

    categoria.delete()

    messages.success(
        request,
        'Categoría eliminada correctamente.'
    )

    return redirect('home:crud_categoria')

def login_view(request):
    return render(request, 'home/login.html')

def noticia(request, pk=None):

    if pk and es_operador(request.user):
        qs = Publicacion.objects.all()
    else:
        qs = Publicacion.objects.filter(estado='publicado')

    qs = qs.select_related(
        'categoria',
        'autor',
        'imagen_portada'
    )

    publicacion = (
        get_object_or_404(qs, pk=pk)
        if pk
        else qs.order_by('-createdat').first()
    )

    if not publicacion:
        messages.info(
            request,
            'Todavía no hay noticias publicadas.'
        )
        return redirect('home:index')

    Publicacion.objects.filter(pk=publicacion.pk).update(
        visitas=F('visitas') + 1
    )

    publicacion.refresh_from_db()

    if request.method == 'POST':

        if not request.user.is_authenticated:
            messages.error(
                request,
                'Debes iniciar sesión para comentar.'
            )
            return redirect('home:login')

        contenido = request.POST.get('contenido', '').strip()

        if contenido:
            Comentario.objects.create(
                publicacion=publicacion,
                user=request.user,
                contenido=contenido
            )

            messages.success(
                request,
                'Comentario enviado. Será visible cuando lo apruebe el administrador.'
            )

        return redirect(
            'home:noticia_detalle',
            pk=publicacion.pk
        )

    recientes = Publicacion.objects.filter(
        estado='publicado'
    ).exclude(
        pk=publicacion.pk
    ).order_by('-createdat')[:4]

    comentarios = publicacion.comentarios.filter(
        estado='aprobado'
    ).select_related(
        'user'
    ).order_by('-createdat')

    categorias = Categoria.objects.all().order_by('nombre')

    return render(
        request,
        'home/noticia.html',
        {
            'publicacion': publicacion,
            'recientes': recientes,
            'comentarios': comentarios,
            'categorias': categorias,
        }
    )



@login_required
def perfil(request):
    perfil_usuario, _ = Perfil.objects.get_or_create(
        user=request.user
    )

    return render(
        request,
        'home/perfil.html',
        {'perfil_usuario': perfil_usuario}
    )


def sign_up(request):
    if request.method == 'POST':

        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        apellido_paterno = request.POST.get('apellido_paterno', '').strip()
        apellido_materno = request.POST.get('apellido_materno', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        # Validar campos
        if not username or not email or not password1:
            messages.error(request, 'Completa los campos obligatorios.')
            return redirect('home:signup')

        # Comprobar contraseñas
        if password1 != password2:
            messages.error(request, 'Las contraseñas no coinciden.')
            return redirect('home:signup')

        # Verificar usuario existente
        if User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya está en uso.')
            return redirect('home:signup')

        # Verificar correo existente
        if User.objects.filter(email=email).exists():
            messages.error(request, 'El correo electrónico ya está registrado.')
            return redirect('home:signup')

        # Crear usuario en Django
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password1
        )

        user.first_name = first_name
        user.last_name = ' '.join(
            filter(None, [apellido_paterno, apellido_materno])
        )
        user.save()

        # Recuperar el perfil creado automáticamente por Signals
        perfil, created = Perfil.objects.get_or_create(user=user)

        perfil.apellido_paterno = apellido_paterno
        perfil.apellido_materno = apellido_materno
        perfil.save()

        messages.success(
            request,
            'Tu cuenta ha sido creada con éxito. Ahora puedes iniciar sesión.'
        )

        return redirect('home:login')

    return render(request, 'home/sign_up.html')

# EDITAR USUARIO
@operador_required

@operador_required
def editar_usuario(request, pk):
    usuario = get_object_or_404(User, pk=pk)
    perfil, _ = Perfil.objects.get_or_create(user=usuario)

    # Un editor no puede modificar a un administrador
    if usuario.is_superuser and not request.user.is_superuser:
        messages.error(
            request,
            'No tienes permisos para editar administradores.'
        )
        return redirect('home:crud_usuarios')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        apellido_paterno = request.POST.get('apellido_paterno', '').strip()
        apellido_materno = request.POST.get('apellido_materno', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        if not username:
            messages.error(request, 'El usuario es obligatorio.')
            return redirect('home:editar_usuario', pk=pk)

        if User.objects.filter(username=username).exclude(pk=pk).exists():
            messages.error(request, 'Ese nombre de usuario ya existe.')
            return redirect('home:editar_usuario', pk=pk)

        if email and User.objects.filter(email=email).exclude(pk=pk).exists():
            messages.error(request, 'Ese correo ya está registrado.')
            return redirect('home:editar_usuario', pk=pk)

        # Validación de contraseñas
        if password1 or password2:
            if password1 != password2:
                messages.error(request, 'Las contraseñas no coinciden.')
                return redirect('home:editar_usuario', pk=pk)

            try:
                validate_password(password1, user=usuario)
            except ValidationError as error:
                for mensaje in error.messages:
                    messages.error(request, mensaje)
                return redirect('home:editar_usuario', pk=pk)

            usuario.set_password(password1)

        # Solo los administradores pueden modificar roles.
        # Tampoco se permite cambiar el rol de la propia cuenta.
        if request.user.is_superuser and usuario.pk != request.user.pk:
            rol = request.POST.get('rol', '')

            if rol not in ('colaborador', 'editor', 'administrador'):
                messages.error(request, 'Selecciona un rol válido.')
                return redirect('home:editar_usuario', pk=pk)

            usuario.is_staff = rol in ('editor', 'administrador')
            usuario.is_superuser = rol == 'administrador'

        # Actualizar datos personales
        usuario.username = username
        usuario.email = email
        usuario.first_name = first_name
        usuario.last_name = ' '.join(
            filter(None, [apellido_paterno, apellido_materno])
        )

        perfil.apellido_paterno = apellido_paterno
        perfil.apellido_materno = apellido_materno

        usuario.save()
        perfil.save()

        # Mantener la sesión si el usuario cambia su propia contraseña
        if usuario.pk == request.user.pk and (password1 or password2):
            update_session_auth_hash(request, usuario)

        messages.success(
            request,
            'Usuario actualizado correctamente.'
        )
        return redirect('home:crud_usuarios')

    return render(request, 'home/crear_usuario.html', {
        'usuario_editado': usuario,
        'perfil_editado': perfil,
    })

    usuario = get_object_or_404(User, pk=pk)
    perfil, _ = Perfil.objects.get_or_create(user=usuario)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        apellido_paterno = request.POST.get('apellido_paterno', '').strip()
        apellido_materno = request.POST.get('apellido_materno', '').strip()
        rol = request.POST.get('rol', 'colaborador')
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')

        if not username:
            messages.error(request, 'El nombre de usuario es obligatorio.')
            return redirect('home:editar_usuario', pk=pk)

        if User.objects.filter(username=username).exclude(pk=pk).exists():
            messages.error(request, 'El nombre de usuario ya existe.')
            return redirect('home:editar_usuario', pk=pk)

        if email and User.objects.filter(email=email).exclude(pk=pk).exists():
            messages.error(request, 'El correo electrónico ya está registrado.')
            return redirect('home:editar_usuario', pk=pk)

        if rol not in ('colaborador', 'editor', 'administrador'):
            messages.error(request, 'Selecciona un rol válido.')
            return redirect('home:editar_usuario', pk=pk)

        if password1 or password2:
            if password1 != password2:
                messages.error(request, 'Las contraseñas no coinciden.')
                return redirect('home:editar_usuario', pk=pk)

            try:
                validate_password(password1, user=usuario)
            except ValidationError as error:
                for mensaje in error.messages:
                    messages.error(request, mensaje)
                return redirect('home:editar_usuario', pk=pk)

            usuario.set_password(password1)

        # Evitar cambiar los propios permisos desde esta pantalla
        if usuario.pk != request.user.pk:
            usuario.is_staff = rol in ('editor', 'administrador')
            usuario.is_superuser = rol == 'administrador'

        usuario.username = username
        usuario.email = email
        usuario.first_name = first_name
        usuario.last_name = ' '.join(
            filter(None, [apellido_paterno, apellido_materno])
        )

        perfil.apellido_paterno = apellido_paterno
        perfil.apellido_materno = apellido_materno

        usuario.save()
        perfil.save()

        messages.success(request, 'Usuario actualizado correctamente.')
        return redirect('home:crud_usuarios')

    return render(request, 'home/crear_usuario.html', {
        'usuario_editado': usuario,
        'perfil_editado': perfil,
    })


# BLOQUEAR O DESBLOQUEAR USUARIO
@operador_required
@require_POST
def bloquear_usuario(request, pk):
    usuario = get_object_or_404(User, pk=pk)

    if usuario.pk == request.user.pk:
        messages.error(request, 'No puedes bloquear tu propia cuenta.')

    elif usuario.is_superuser and not request.user.is_superuser:
        messages.error(request, 'No tienes permisos para bloquear administradores.')

    else:
        usuario.is_active = not usuario.is_active
        usuario.save(update_fields=['is_active'])

        messages.success(
            request,
            'Estado del usuario actualizado correctamente.'
        )

    return redirect('home:crud_usuarios')


# ELIMINAR USUARIO
@operador_required
@require_POST
def eliminar_usuario(request, pk):
    usuario = get_object_or_404(User, pk=pk)

    if usuario.pk == request.user.pk:
        messages.error(request, 'No puedes eliminar tu propia cuenta.')

    elif usuario.is_superuser and not request.user.is_superuser:
        messages.error(request, 'No tienes permisos para eliminar administradores.')

    else:
        usuario.delete()
        messages.success(request, 'Usuario eliminado correctamente.')

    return redirect('home:crud_usuarios')

