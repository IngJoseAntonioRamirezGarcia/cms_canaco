from home.models import Categoria, Publicacion, Perfil

def global_categorias(request):
    perfil_usuario = None

    if request.user.is_authenticated:
        perfil_usuario = Perfil.objects.filter(
            user=request.user
        ).first()

    return {
        'global_categorias': Categoria.objects.all().order_by('nombre'),
        'global_recientes': Publicacion.objects.filter(
            estado=Publicacion.ESTADO_PUBLICADO
        ).order_by('-createdat')[:3],
        'perfil_usuario': perfil_usuario,
    }