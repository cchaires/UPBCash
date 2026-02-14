# Gap List de Migracion (HTML+CSS -> Django)

## Estado actual
- Proyecto Django actual: render de templates sin logica backend de negocio.
- Carpeta HTML+CSS: mas pantallas y funciones de frontend.

## Prioridad alta
1. Registro y registro invitado (rutas, templates, validacion JS, enlaces desde login) - completado en esta iteracion.
2. Modulo Cliente expandido:
   - `menu_alimentos` - completado.
   - `carrito` - completado.
   - `cliente_mapa` - completado.
   - `historial_compras` - completado.
   - `historial_recargas` y formularios de reporte - completado.
3. Modulo Vendedor expandido:
   - `menu_vendedor` - completado.
   - `mapa_vendedor` - completado.
   - `historial_ventas_vendedor` - completado.
4. Modulo Administrador:
   - `admin_inicio` - completado.
   - `admin_mapa` - completado.

## Prioridad media
5. Unificar comportamiento de recarga:
   - Mantener/recuperar logica de saldo con `localStorage` mientras no exista backend. - completado.
6. Integrar assets compartidos (imagenes/mapa) en `static/` de Django y corregir referencias.
   - completado.
7. Normalizar navegacion por `url` names en todos los templates migrados.
   - completado.

## Prioridad baja
8. Reemplazar logica de frontend temporal por backend real:
   - autenticacion (login/registro/logout) - completado.
   - modelos base de persistencia (`UserProfile`, `Wallet`, `Recharge`, `RechargeIssue`) - completado.
   - persistencia backend de recargas e historial de recargas/reportes - completado.
   - persistencia backend de carrito/compras e historial de compras - completado.

## Infraestructura (nuevo)
9. Preparar base de datos productiva:
   - configuracion Django para `PostgreSQL` via variables de entorno con fallback `SQLite` - completado.
   - `docker-compose` para levantar servicio `PostgreSQL` local - completado.
   - ledger de wallet (`WalletLedger`) para trazabilidad de saldo - completado.
