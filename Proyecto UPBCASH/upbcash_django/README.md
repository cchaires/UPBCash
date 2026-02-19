# UPBCash Django

Aplicacion web de UPBCash para gestion de UCoins por eventos/campanas con roles cliente/vendedor/staff, catalogo por puesto, ordenes con QR y contabilidad en doble partida.

## Estado del proyecto

- Esquema multi-evento implementado en PostgreSQL/SQLite con nuevas apps de dominio:
  - `events`: campanas, membresias y grupos por evento.
  - `stalls`: mapa, puestos, catalogo e inventario.
  - `commerce`: carrito v2, ordenes, QR y entrega.
  - `accounting`: ledger de doble partida, recargas y saldo cache.
  - `operations`: soporte y auditoria staff.
- API base para operaciones clave:
  - checkout: `POST /api/events/{event_id}/cart/checkout`
  - validacion QR: `POST /api/orders/{order_id}/qr/verify`
  - staff: `assign-vendor`, `assign-spot`, `grant-ucoins`
- Dual-write habilitado desde flujos legacy de `core` (`recarga` y `checkout`) hacia el nuevo esquema.
- Cierre de evento soportado por comando de gestion con expiracion de saldo remanente.

## Stack

- Python 3
- Django 5
- PostgreSQL 16 (opcional para desarrollo/productivo)
- SQLite (fallback local)

## Estructura principal

- `core/`: modulo legacy (pantallas actuales) con sincronizacion a esquema nuevo.
- `events/models.py`: eventos, membresias y roles por contexto.
- `stalls/models.py`: mapa, puestos, asignaciones, catalogo e inventario.
- `commerce/models.py`: carrito/ordenes/QR/entrega.
- `accounting/models.py`: cuentas, transacciones, asientos, recargas y saldos.
- `operations/models.py`: tickets de soporte y auditoria staff.
- `core/templates/core/`: templates migrados.
- `static/core/`: css/js/img compartidos.
- `upbcash/settings.py`: configuracion por entorno.
- `docker-compose.yml`: servicio local de PostgreSQL.
- `.env.example`: variables de entorno de referencia.
- `MIGRACION_GAPS.md`: checklist de migracion (actualizado a completado en bloques trabajados).

## Modelo de datos (resumen v2)

- `events_eventcampaign`, `events_eventmembership`, `events_eventusergroup`
- `stalls_mapzone`, `stalls_mapspot`, `stalls_stall`, `stalls_stallassignment`
- `stalls_catalogproduct`, `stalls_stallproduct`, `stalls_stockmovement`
- `commerce_cartitem`, `commerce_salesorder`, `commerce_salesorderitem`
- `commerce_orderqrtoken`, `commerce_orderdeliverylog`
- `accounting_ledgeraccount`, `accounting_ledgertransaction`, `accounting_ledgerentry`
- `accounting_walletbalancecache`, `accounting_topuprecord`, `accounting_staffcreditgrant`
- `operations_supportticket`, `operations_staffauditlog`

## Reglas clave implementadas

- Multi-evento obligatorio.
- Usuario nuevo entra a grupo `cliente` del evento activo.
- Inventario por producto con modo `finite` o `unlimited`.
- Umbral configurable de bajo inventario (`low_stock_threshold`).
- QR por orden con token hash rotativo/revocable.
- UCoin con paridad fija `1 UCoin = 1 MXN`.
- Transacciones contables balanceadas (trigger en PostgreSQL + validacion en servicio).
- Evento cerrado queda en modo solo lectura y puede expirar saldos con `close_event`.

## Configuracion de entorno

Crear archivo `.env` basado en `.env.example`.

Variables clave:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DB_ENGINE` (`sqlite` o `postgresql`)
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_CONN_MAX_AGE`
- `POSTGRES_PORT` (para docker compose)

## Ejecucion local (SQLite)

```bash
cd "Proyecto UPBCASH/upbcash_django"
./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py migrate
./venv/bin/python manage.py runserver
```

## Ejecucion local (PostgreSQL con Docker)

```bash
cd "Proyecto UPBCASH/upbcash_django"
cp .env.example .env
# Ajustar password/host si aplica

docker compose up -d db
./venv/bin/pip install -r requirements.txt
./venv/bin/python manage.py migrate
./venv/bin/python manage.py runserver
```

## Backfill y cierre de evento

```bash
# Migrar datos legacy de core al esquema v2
DB_ENGINE=sqlite ./venv/bin/python manage.py backfill_v2 --event-code legacy-boot --event-name "Evento Legacy"

# Cerrar evento y expirar saldos
DB_ENGINE=sqlite ./venv/bin/python manage.py close_event legacy-boot
```

## Comandos utiles

```bash
./venv/bin/python manage.py check
./venv/bin/python manage.py makemigrations
./venv/bin/python manage.py migrate
./venv/bin/python manage.py test
./venv/bin/python manage.py createsuperuser
```
