# UPBCash Django

Aplicacion web de UPBCash para gestion de UCoins por eventos/campanas con roles cliente, vendedor y staff.

## Estado actual del proyecto

- Esquema V2 multi-evento activo en apps de dominio:
  - `events`: campanas, membresias y grupos por evento.
  - `stalls`: mapa, puestos, asignaciones, catalogo e inventario.
  - `commerce`: carrito V2, ordenes, QR y entrega.
  - `accounting`: ledger de doble partida, recargas y saldos.
  - `operations`: auditoria staff y operaciones de soporte.
- Flujos cliente y vendedor integrados con V2 en pantallas `core/*`.
- Panel staff implementado en `GET/POST /staff/`.
- Soporte de imagenes de producto con `MEDIA_URL`/`MEDIA_ROOT` y fallback visual por categoria/subcategoria.
- Base de datos soportada:
  - PostgreSQL (recomendado).
  - SQLite (fallback local).

## Novedades implementadas

### 1) Panel staff y control de acceso por rol

- Ruta staff: `GET/POST /staff/`.
- Reglas en `/vendedor/*`:
  - Requiere rol `vendedor` en evento activo.
  - Si usuario tiene `staff` pero no `vendedor`, redirecciona a `/staff/`.
  - Si no tiene `vendedor` ni `staff`, redirecciona a `/cliente/`.
- Dropdown de usuario condicionado por banderas globales:
  - `can_view_vendor`
  - `can_view_staff`
  - `can_view_admin`
  - `active_event_code`
- Gestion de permisos desde staff:
  - `grant_role` y `revoke_role` para `vendedor|staff`.
  - Bloqueo de auto-revocacion del rol `staff`.
  - Bitacora en `operations.StaffAuditLog`.

### 2) Productos V2 por vendedor

- Alta/edicion desde `vendedor/productos`.
- Clasificacion:
  - Categoria y subcategoria.
  - Naturaleza: `Inventariable` / `No inventariable`.
- Inventario:
  - Umbral automatico de bajo inventario al 15%.
  - Aviso de "Proximo a agotarse" en menu cliente cuando aplica.
- Costeo y precio:
  - `cost_ucoin` y `price_ucoin` por producto.
- Imagen:
  - Subida opcional.
  - Fallback por taxonomia si no hay imagen cargada.

### 3) Flujo cliente V2

- Menu por puesto basado en `stalls.StallProduct`.
- Carrito V2 con `commerce.CartItem`.
- Checkout V2 con `CheckoutService`.
- Historial de compras V2 con `SalesOrder` y `SalesOrderItem`.

## Arquitectura y modulos

- `core/`: UI legacy con integracion al esquema V2.
- `events/`: contexto de evento, membresias y roles.
- `stalls/`: puestos, mapa, inventario y productos.
- `commerce/`: carrito, ordenes, QR y entrega.
- `accounting/`: ledger, recargas, saldos y movimientos.
- `operations/`: auditoria, soporte y acciones staff.
- `upbcash/settings.py`: configuracion por entorno y DB.
- `docker-compose.yml`: servicios de desarrollo (`db` y `web`).

## Requisitos por sistema operativo

## Compatibilidad minima

- Python 3.11 o superior.
- Docker Engine/Desktop con Compose v2.
- Git.

## Windows (PowerShell)

1. Instalar:
   - Python 3.11+ (activar "Add Python to PATH").
   - Git.
   - Docker Desktop (recomendado con WSL2 habilitado).
2. Verificar:

```powershell
python --version
docker --version
docker compose version
```

3. Si PowerShell bloquea activacion del venv:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl ca-certificates docker.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Cierra sesion y vuelve a entrar para aplicar grupo docker.
```

Verificacion:

```bash
python3 --version
docker --version
docker compose version
```

## Fedora

```bash
sudo dnf install -y python3 python3-pip python3-virtualenv git docker docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Cierra sesion y vuelve a entrar para aplicar grupo docker.
```

Verificacion:

```bash
python3 --version
docker --version
docker compose version
```

## Variables de entorno

1. Crear `.env` desde `.env.example`.
2. Configurar secreto y credenciales reales para tu entorno.

```bash
cp .env.example .env
```

Variables clave:

- `DJANGO_SECRET_KEY`: clave de aplicacion.
- `DJANGO_DEBUG`: `True`/`False`.
- `DJANGO_ALLOWED_HOSTS`: hosts permitidos por Django.
- `DJANGO_PORT`: puerto publicado para app (modo Docker web).
- `DB_ENGINE`: `postgresql` o `sqlite`.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`.
- `DB_HOST`, `DB_PORT`, `DB_CONN_MAX_AGE`.
- `POSTGRES_PORT`: puerto local publicado para contenedor de PostgreSQL.

Diferencia de `DB_HOST`:

- Modo host + DB Docker: `DB_HOST=127.0.0.1`.
- Modo full Docker (web + db): el servicio `web` fuerza `DB_HOST=db` desde `docker-compose.yml`.

## Instalacion local sin Docker web (host + DB Docker)

Este modo ejecuta Django en tu SO y PostgreSQL en contenedor.

1. Posicionarte en proyecto:

```bash
cd "Proyecto UPBCASH/upbcash_django"
cp .env.example .env
```

2. Levantar PostgreSQL:

```bash
docker compose up -d db
```

3. Crear y activar entorno virtual.

Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

4. Migrar y correr servidor:

```bash
python manage.py migrate
python manage.py runserver
```

5. Abrir:

- `http://127.0.0.1:8000`

## Instalacion y ejecucion full Docker (Django + PostgreSQL)

Este modo ejecuta app y DB en contenedores.

1. Preparar entorno:

```bash
cd "Proyecto UPBCASH/upbcash_django"
cp .env.example .env
```

2. Construir e iniciar servicios:

```bash
docker compose up -d db
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py createsuperuser
docker compose up --build web db
```

3. Abrir app:

- `http://127.0.0.1:${DJANGO_PORT:-8000}`

4. Comandos utiles en modo Docker:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py test core.tests operations.tests
docker compose logs -f web
docker compose logs -f db
```

## Migraciones, pruebas y comandos de validacion

En host (venv activo):

```bash
python manage.py check
python manage.py makemigrations
python manage.py migrate
python manage.py test core.tests operations.tests
```

En Docker:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py test core.tests operations.tests
```

## Inicializacion de usuarios y roles

## Superusuario Django

```bash
python manage.py createsuperuser
```

## Asignar rol staff o vendedor en evento activo

```bash
python manage.py shell
```

```python
from django.contrib.auth import get_user_model
from events.services import get_active_event, assign_group_to_user

User = get_user_model()
user = User.objects.get(username="staff")
event = get_active_event()
assign_group_to_user(event=event, user=user, group_name="staff")
# assign_group_to_user(event=event, user=user, group_name="vendedor")
```

## Comandos de operacion y mantenimiento

Backfill legacy a V2:

```bash
python manage.py backfill_v2 --event-code legacy-boot --event-name "Evento Legacy"
```

Cerrar evento y expirar saldos:

```bash
python manage.py close_event legacy-boot
```

## API y rutas clave

## Web

- `GET /cliente/`
- `GET /cliente/menu/`
- `GET /cliente/carrito/`
- `GET /vendedor/`
- `GET /vendedor/productos/`
- `GET /vendedor/ventas/`
- `GET /vendedor/mapa/`
- `GET/POST /staff/`

## API

- `POST /api/events/{event_id}/cart/checkout`
- `POST /api/orders/{order_id}/qr/verify`
- `POST /api/events/{event_id}/staff/assign-vendor`
- `POST /api/events/{event_id}/staff/assign-spot`
- `POST /api/events/{event_id}/staff/grant-ucoins`

## Checklist de verificacion funcional

1. Login correcto en `index`.
2. Menu cliente carga productos por puesto.
3. Badge de "Proximo a agotarse" aparece en productos con regla 15%.
4. Carrito y checkout generan orden V2.
5. Usuario staff entra a `/staff/` y puede buscar usuarios.
6. Usuario sin rol vendedor no entra a `/vendedor/*`.
7. Usuario vendedor puede abrir panel vendedor.
8. Historial de compras muestra ordenes V2.

## Datos y persistencia (PostgreSQL Docker)

- Volumen persistente: `postgres_data`.
- Ver volumenes:

```bash
docker volume ls
```

## Backup rapido (desarrollo)

Linux/macOS:

```bash
mkdir -p backups
docker compose exec -T db pg_dump -U upbcash -d upbcash > backups/upbcash_dev.sql
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force backups | Out-Null
docker compose exec -T db pg_dump -U upbcash -d upbcash | Out-File backups\upbcash_dev.sql -Encoding utf8
```

## Restore rapido (desarrollo)

Linux/macOS:

```bash
cat backups/upbcash_dev.sql | docker compose exec -T db psql -U upbcash -d upbcash
```

Windows PowerShell:

```powershell
Get-Content backups\upbcash_dev.sql | docker compose exec -T db psql -U upbcash -d upbcash
```

## Troubleshooting

1. `ModuleNotFoundError: No module named 'django'`
- Instala dependencias en venv: `pip install -r requirements.txt`.

2. `django.db.utils.OperationalError` (conexion a DB)
- Verifica que `db` este arriba: `docker compose ps`.
- Revisa `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`.
- En host usa `DB_HOST=127.0.0.1`; en contenedor web usa `DB_HOST=db`.

3. `permission denied while trying to connect to the Docker daemon socket`
- Linux: agrega usuario al grupo docker y vuelve a iniciar sesion.

4. Puerto ocupado (`5432` o `8000`)
- Cambia `POSTGRES_PORT` o `DJANGO_PORT` en `.env`.

5. Cambios en modelos sin aplicar
- Ejecuta: `python manage.py makemigrations && python manage.py migrate`.

## Recomendaciones operativas

1. No usar secretos o passwords de ejemplo fuera de desarrollo.
2. Cambiar `DJANGO_SECRET_KEY` por una clave fuerte en cada entorno.
3. Mantener `DJANGO_DEBUG=False` en ambientes no locales.
4. Restringir `DJANGO_ALLOWED_HOSTS` a dominios necesarios.
5. No publicar PostgreSQL directamente en internet.
6. Mantener `.env` fuera de control de versiones.
7. Programar backups periodicos si la data es relevante.

## Alcance de esta guia

Esta guia cubre desarrollo local y validacion funcional reproducible (host+DB Docker y full Docker). No cubre despliegue productivo avanzado (Nginx/Gunicorn/Kubernetes).
