from pathlib import Path
import os

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "django-insecure-dev-only")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

default_allowed_hosts = "127.0.0.1,localhost,chat-bot-salud.onrender.com"
render_external_hostname = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if render_external_hostname:
    default_allowed_hosts = f"{default_allowed_hosts},{render_external_hostname}"

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", default_allowed_hosts).split(",")
    if host.strip()
]

# Host del modulo interno de gestion. En produccion: seleccion.cmvalparaiso.cl
# El setting se sigue llamando GESTION_HOST porque nombra a la app `gestion`;
# lo que cambia es el hostname publico con que se accede a ella.
GESTION_HOST = os.getenv("GESTION_HOST", "gestion.localhost")
if GESTION_HOST and GESTION_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(GESTION_HOST)

# Origenes de confianza para CSRF (esquema + host), necesario con DEBUG=False
# detras de un dominio HTTPS. Ej: https://morbilidad.cmvalparaiso.cl
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

# Detras de nginx que termina TLS: confiar en X-Forwarded-Proto para que
# Django reconozca la request como segura (HTTPS). Se activa solo en produccion.
if os.getenv("USE_PROXY_SSL_HEADER", "False").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Misma condicion de produccion: exigir HTTPS para las cookies de sesion
    # y CSRF. En local se sirve por HTTP y esto rompe el login, por eso no se
    # activa incondicionalmente.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Acota a 8 horas la ventana en que una sesion sigue viva despues de revocar
# un acceso (desmarcar PerfilUsuario.activo o User.is_active): la sesion
# ahora transporta acceso a datos de salud, no solo al admin.
SESSION_COOKIE_AGE = 28800

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "mozilla_django_oidc",
    "solicitudes",
    "gestion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "cesfam_chatbot.middleware.HostBasedUrlconfMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cesfam_chatbot.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "cesfam_chatbot.wsgi.application"

if os.getenv("DB_ENGINE", "mysql").lower() == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.getenv("SQLITE_NAME", BASE_DIR / "db.sqlite3"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("DB_NAME", "chat_bot_salud"),
            "USER": os.getenv("DB_USER", "root"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "3306"),
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-cl"
TIME_ZONE = "America/Santiago"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Autenticacion OIDC con Google Workspace -------------------------------
# El modulo de gestion se entra solo con cuenta institucional de Google. La
# identidad la da Google; el rol y el centro los da gestion.PerfilUsuario.

# Dominio institucional. Se valida contra el claim "hd" del ID token, no
# contra el parametro de la request: el parametro es solo una pista de UI.
GOOGLE_WORKSPACE_DOMAIN = os.getenv("GOOGLE_WORKSPACE_DOMAIN", "cmvalparaiso.cl")

OIDC_RP_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
OIDC_RP_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")

# Endpoints publicos de Google (estables, documentados en su discovery doc:
# https://accounts.google.com/.well-known/openid-configuration).
OIDC_OP_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
OIDC_OP_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
OIDC_OP_USER_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
OIDC_OP_JWKS_ENDPOINT = "https://www.googleapis.com/oauth2/v3/certs"
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_RP_SCOPES = "openid email profile"

AUTHENTICATION_BACKENDS = [
    "gestion.auth.OIDCAuthenticationBackendGestion",
    # Se mantiene el backend por password solo para superusuarios operando
    # el admin de Django; los funcionarios entran unicamente por Google.
    "django.contrib.auth.backends.ModelBackend",
]

# Nunca crear cuentas al vuelo: el alta la hace un ADMIN dando de alta el
# perfil. Un correo del dominio sin perfil queda rechazado.
OIDC_CREATE_USER = False

# "hd" acota el selector de cuentas de Google al dominio institucional;
# "prompt" evita quedar pegado en la ultima cuenta usada.
OIDC_AUTH_REQUEST_EXTRA_PARAMS = {
    "hd": GOOGLE_WORKSPACE_DOMAIN,
    "prompt": "select_account",
}

LOGIN_URL = "gestion:login"
LOGIN_REDIRECT_URL = "/"
LOGIN_REDIRECT_URL_FAILURE = "/sin-acceso/"
LOGOUT_REDIRECT_URL = "/sin-acceso/"
