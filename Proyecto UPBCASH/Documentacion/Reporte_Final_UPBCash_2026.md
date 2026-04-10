# UNIVERSIDAD POLITECNICA DE BAJA CALIFORNIA
## COORDINACION DE TECNOLOGIAS

# Reporte Final - Proyecto Integrador I

## UPBCash: Sistema para la gestion y control de ingresos en eventos escolares

**Presentan:**

- Pedro Alejandro Aparicio Herrera
- Oliver Moreno Gallegos
- Alan Vega Millan
- Carlos Arturo Chaires Armenta

**Docente:** Hector Alonso Noriega Garcia  
**Campus:** Mexicali, Baja California  
**Periodo de referencia de la plantilla:** enero - marzo de 2026  
**Fuente de verdad tecnica usada en este reporte:** estado actual del repositorio `upbcash_django` y documentacion de evidencia disponible

---

## 1.1 Resumen de actividades realizadas durante el periodo del proyecto (enero - marzo)

Durante el desarrollo del proyecto integrador se trabajo en la definicion, construccion y consolidacion de UPBCash, un sistema web orientado a mejorar la organizacion, control y transparencia de los ingresos generados en eventos escolares como kermeses, noches mexicanas y actividades institucionales. El problema identificado desde las primeras etapas fue la dependencia de procesos manuales para registrar ventas, controlar efectivo y asignar responsabilidades operativas, lo cual provoca errores de captura, poca trazabilidad, dificultades para auditar y baja visibilidad del comportamiento financiero de cada evento. A partir de esa necesidad se definio una solucion digital basada en un sistema de informacion automatizado que permitiera centralizar usuarios, eventos, puestos, recargas, compras y operaciones de staff dentro de una misma plataforma.

En la fase de analisis y diseno se delimitaron los principales actores del sistema y sus responsabilidades operativas. Se establecieron perfiles de cliente, vendedor, staff y administrador, asi como reglas de acceso asociadas al contexto de cada evento. En paralelo se construyo una arquitectura modular que hoy se encuentra reflejada en el backend Django del proyecto: `events` para el contexto de campanas y membresias; `stalls` para puestos, mapa, productos e inventario; `commerce` para carrito, ordenes y flujo de compra; `accounting` para ledger, saldos y recargas; `operations` para auditoria y soporte staff; y `core` para vistas, navegacion y experiencia web. Esta separacion por dominios permitio ordenar el crecimiento del sistema y sentar una base mantenible para futuras ampliaciones.

Otro bloque importante de actividades fue el modelado de datos. El proyecto evoluciono desde una vision inicial mas simple hasta una estructura relacional mas completa para soportar multiples eventos, asignaciones de puestos, membresias por evento, catalogo de productos, control de stock, movimientos de inventario, recargas de UCoins y trazabilidad financiera. La implementacion actual incluye soporte para PostgreSQL como base recomendada y SQLite como alternativa local, ademas de configuracion por variables de entorno para facilitar despliegues en diferentes escenarios. Tambien se incorporo un `docker-compose.yml` para estandarizar el entorno de desarrollo.

En el frente de desarrollo se construyeron y refinaron los flujos principales del sistema. Para clientes se implementaron vistas de menu, carrito, checkout, historial de compras, historial de recargas y visualizacion del mapa. Para vendedores se habilitaron funciones de gestion de tienda, alta y edicion de productos, control de imagenes, inventario y consulta de ventas. Para staff se desarrollaron vistas y APIs de administracion orientadas a gestionar eventos, asignar vendedores a puestos, asignar espacios del mapa, otorgar UCoins y sincronizar roles. Adicionalmente, el sistema contempla verificacion por QR para la entrega de pedidos y una bitacora de operaciones staff orientada a la trazabilidad.

En materia de interfaz y experiencia de usuario se trabajo con una linea visual unificada en cliente, vendedor, staff, cuenta y autenticacion. La documentacion de UX incluida en el proyecto muestra el uso de user persona, wireframes, mockups y pruebas guiadas con usuarios invitados simulados. Los reportes de prueba reflejan que los flujos principales se comprendieron con rapidez y que las observaciones obtenidas se centraron en aspectos de jerarquia visual, claridad de validaciones y carga cognitiva en formularios complejos. Esto confirma que el desarrollo no se enfoco solo en la funcionalidad tecnica, sino tambien en la usabilidad del sistema.

En seguridad y control de acceso se implementaron mejoras relevantes. La evidencia tecnica disponible documenta la correccion de accesos indebidos al panel administrativo, el endurecimiento de configuraciones de despliegue en Django y la validacion de `DJANGO_SECRET_KEY` segura cuando la aplicacion se ejecuta en produccion. A nivel de logica de negocio se establecieron snapshots de autorizacion, validaciones por permisos y bloqueos por ventana de evento para distinguir claramente lo que puede hacer cada rol dentro de una campana. Estas decisiones reducen riesgos operativos y fortalecen la confiabilidad del sistema.

En pruebas, la documentacion del proyecto reporta una corrida automatizada de 44 pruebas satisfactorias y verificaciones adicionales de seguridad con `manage.py check --deploy`. Dentro del codigo actual existen pruebas para flujos de vistas V2, control de acceso a panel staff y admin, bloqueos por evento, permisos de API, sistema visual y operaciones integradas de compra, recarga y entrega por QR. En conjunto, estas actividades muestran que el proyecto avanzo desde la definicion del problema hasta una solucion funcional con base tecnica consistente, evidencia de validacion y una arquitectura preparada para seguir creciendo.

---

## 2.1 Propósito

El presente Plan de Desarrollo de Software tuvo como proposito guiar la construccion de UPBCash como un sistema de informacion automatizado orientado a digitalizar la gestion operativa y financiera de eventos escolares. Durante el periodo de trabajo se busco sustituir practicas manuales de registro por un flujo estructurado capaz de administrar usuarios, eventos, ventas, recargas y reportes dentro de una sola plataforma web. El plan se apoyo en una estrategia incremental: primero definir el problema y las necesidades del entorno escolar, despues modelar la informacion y los actores del sistema, y finalmente implementar los modulos clave para llevar esas reglas al software.

De forma especifica, el plan persiguio tres objetivos: construir una base de datos suficientemente robusta para soportar operaciones reales, desarrollar una aplicacion web organizada por dominios funcionales y validar la solucion mediante pruebas tecnicas y de experiencia de usuario. El resultado esperado no era solamente un prototipo visual, sino una base operativa que permitiera controlar ingresos por evento, reducir errores humanos, mejorar la trazabilidad de cada transaccion y dejar documentadas buenas practicas de seguridad, despliegue y mantenimiento para futuras iteraciones del proyecto.

---

## 2.2 Ámbito de responsabilidad

Para efectos del reporte final, las responsabilidades se describen como funciones del equipo de trabajo y no se asignan a una persona especifica, ya que la evidencia disponible no fija una correspondencia individual concluyente.

| Sigla | Responsabilidad | Aplicacion en UPBCash |
| --- | --- | --- |
| RGPY | Responsable de Gestion de Proyectos | Coordinar el avance general del proyecto, organizar entregables, dar seguimiento a los hitos del periodo, integrar la documentacion y mantener coherencia entre problema, solucion propuesta y resultado alcanzado. |
| RAPE | Responsable de la Administracion de Proyectos | Ordenar evidencias, controlar el cumplimiento de actividades, estructurar reportes y asegurar que los componentes tecnicos, funcionales y documentales se presenten de manera consistente ante la institucion. |
| RDS | Responsable del Desarrollo de Sistemas de Informacion | Disenar, programar, probar e integrar la solucion de software, incluyendo base de datos, backend, interfaz, control de acceso, reglas de negocio, pruebas automatizadas y ajustes derivados de validacion tecnica o de usuario. |

---

## 2.3 Definiciones

| Termino | Definicion aplicada al proyecto |
| --- | --- |
| UCoin | Unidad de saldo digital utilizada por UPBCash para representar recargas, compras y movimientos internos dentro de un evento. |
| Evento / Campaña | Contexto operativo que agrupa fechas, usuarios, puestos, permisos y transacciones. En el codigo actual se modela principalmente mediante `EventCampaign`. |
| Puesto | Espacio o tienda participante en un evento, desde donde un vendedor ofrece productos o servicios. En el sistema se modela con `Stall`. |
| Vendedor | Usuario con permisos para administrar su tienda, productos, imagen, inventario y entrega de pedidos segun el contexto del evento. |
| Cliente | Usuario que consulta el menu, agrega productos al carrito, realiza recargas, compra con UCoins y consulta su historial. |
| Staff | Usuario operativo con permisos para gestionar roles, asignar vendedores, asignar espacios del mapa, otorgar UCoins y realizar acciones de soporte durante el evento. |
| Recarga | Operacion mediante la cual se incrementa el saldo disponible de un cliente dentro del sistema. |
| Orden | Registro formal de una compra realizada por un cliente. En el sistema se representa con `SalesOrder` y sus partidas. |
| QR | Token o codigo asociado a una orden para validar su entrega por parte del vendedor o del personal autorizado. |
| Ledger | Esquema de trazabilidad contable que registra saldos y movimientos financieros para mantener control y consistencia de las transacciones. |

---

## 2.4 Método de Trabajo

**No. I. Criterios, Convenciones y recomendaciones para utilizar este instructivo**

Para la elaboracion de este proyecto se siguio un metodo de trabajo incremental y orientado por evidencia. Cada decision se documento con base en tres fuentes: necesidad detectada en el contexto escolar, implementacion real en el repositorio Django y validacion mediante pruebas tecnicas o de usuario. Se priorizo mantener consistencia terminologica entre la documentacion y el software para que el reporte final refleje el sistema construido y no una propuesta ajena a su estado real.

### 1. Diseño

El diseno del software comenzo con la definicion del problema: los eventos escolares suelen operar con manejo de efectivo, registros manuales y controles dispersos, lo que complica la administracion de ventas, recargas y auditoria. A partir de esa necesidad se establecio que el sistema debia cubrir, como minimo, registro de usuarios, control de eventos, gestion de puestos, venta de productos, control de saldos y generacion de reportes e historiales. La documentacion preliminar del proyecto y el resumen ejecutivo muestran que esta necesidad fue el punto de partida para la propuesta de solucion.

En la parte de experiencia de usuario se trabajaron actividades de conceptualizacion apoyadas en user persona, wireframes y mockups. La evidencia en `USER PERSONA, WIREFRAMES, MOCKUPS e IA.pdf` muestra que el equipo uso un enfoque centrado en usuario para definir flujos claros, lenguaje comprensible y navegacion entendible segun el perfil que interactua con la plataforma. Ese criterio se refleja en la implementacion actual, donde existen experiencias diferenciadas para cliente, vendedor, staff, cuenta y autenticacion, todas sustentadas por layouts, componentes CSS reutilizables e iconografia local.

En arquitectura se adopto una separacion por dominios para evitar un sistema monolitico desordenado. La aplicacion se distribuye en seis modulos principales:

- `events`: administra campañas, membresias y grupos por evento.
- `stalls`: administra puestos, espacios del mapa, productos, imagenes e inventario.
- `commerce`: controla carrito, checkout, ordenes, QR y entrega.
- `accounting`: administra ledger, saldos, recargas y movimientos.
- `operations`: concentra auditoria y operaciones de soporte staff.
- `core`: integra vistas, rutas, formularios, contexto visual y flujos web.

En el modelo de datos se incorporaron entidades que responden a necesidades operativas reales: campañas con ventanas internas y publicas, membresias por evento, grupos de usuario, puestos, asignaciones visuales del mapa, catalogo de productos, productos por puesto, movimientos de stock, carrito, ordenes, tokens QR, recargas y saldos. Esta evolucion permitio pasar de una idea inicial simplificada a una base estructurada y escalable, sin perder la orientacion practica del proyecto.

### 2. Desarrollo de Software

El desarrollo se realizo sobre Django como framework principal, usando Python, templates del lado del servidor, CSS y JavaScript local para la interfaz, y una base de datos configurable por entorno. El proyecto soporta PostgreSQL como motor recomendado y SQLite como alternativa local, lo cual facilita tanto pruebas rapidas como una configuracion mas cercana a produccion. La carga de variables desde `.env`, la separacion de apps y el uso de `docker-compose.yml` forman parte de la estrategia de organizacion del entorno.

Las rutas principales del sistema muestran la cobertura funcional alcanzada. Existen flujos web para autenticacion, registro y recuperacion de acceso; rutas de cliente para menu, carrito, mapa, historial de compras e historial de recargas; rutas de vendedor para tienda, productos, ventas y mapa; rutas de staff para panel, eventos y asignacion de mapa; y rutas API para checkout, verificacion de QR, estado del mapa, asignacion de vendedor, asignacion de espacios y otorgamiento de UCoins. Esta estructura refleja que el sistema no se limito a pantallas estaticas, sino que ya incorpora operaciones transaccionales reales.

Un aspecto central del desarrollo fue el control de acceso. El sistema utiliza perfiles y permisos asociados al evento activo para determinar si un usuario puede actuar como cliente, vendedor, staff o administrador. Esta capa evita que la autorizacion dependa solo de la autenticacion y agrega reglas de negocio asociadas a la ventana del evento. El siguiente fragmento representa esa logica en el backend:

```python
def build_authz_snapshot(*, user, event=None, sync_groups=True):
    resolved_event = event or get_active_campaign()
    if not user or not user.is_authenticated:
        return AuthzSnapshot(event=resolved_event)

    profile_names = set()
    if sync_groups:
        profile_names = sync_auth_profile_groups_for_event(user=user, event=resolved_event)

    is_superuser = bool(user.is_superuser)
    can_bypass_event_lock = is_superuser or ("staff" in profile_names)
    campaign_open = is_campaign_open(resolved_event)
    public_open = is_public_event_open(resolved_event)
```

Con esta base, el proyecto implementa reglas como bloqueo cuando no hay evento activo, acceso diferenciado por rol, verificacion de permisos en web y API, y proteccion adicional para el panel administrativo. En la logica de negocio tambien se desarrollo un flujo de compra completo: el cliente agrega productos al carrito, el sistema valida stock, calcula subtotal y total, descuenta saldo mediante el servicio de wallet, genera la orden, crea el token QR y deja evidencia de inventario y movimientos asociados. Esto conecta interfaz, reglas de negocio y persistencia en una sola operacion.

Adicionalmente, se trabajaron aspectos visuales y de mantenimiento. El sistema cuenta con un esquema de estilos reutilizable basado en tokens, layouts compartidos e includes, lo que permite conservar consistencia entre modulos. La compatibilidad incremental con vistas legadas y la existencia de migraciones V2 muestran que el desarrollo se ejecuto sin perder de vista la evolucion del proyecto.

### 3. Pruebas

La etapa de pruebas se apoyo en evidencia automatizada y en validacion de experiencia de usuario. Como evidencia historica, en la documentacion `02_Pruebas_Automatizadas_Django.pdf` se reporta una corrida de `44 pruebas, OK`, asi como validaciones exitosas de `manage.py check --deploy` cuando se usan parametros seguros de despliegue. Tambien se documenta la falla esperada cuando `DJANGO_SECRET_KEY` no cumple los criterios definidos para produccion, lo cual confirma que las validaciones de seguridad fueron implementadas y comprobadas.

Ademas de esa evidencia documental, se realizo una validacion local actual sobre el estado vigente del repositorio utilizando `DB_ENGINE=sqlite ./venv/bin/python manage.py test --verbosity 1`, con resultado `Ran 48 tests ... OK`. En la misma validacion se ejecuto `DJANGO_DEBUG=False ... ./venv/bin/python manage.py check --deploy`, obteniendo `System check identified no issues (0 silenced).` Esta distincion es importante porque las `44 pruebas` corresponden a una evidencia historica de una iteracion previa, mientras que las `48 pruebas` reflejan el estado actual comprobado del proyecto.

En el codigo actual existen pruebas enfocadas en areas relevantes del sistema, entre ellas:

- flujos V2 de vistas para menu, carrito, mapa y productos;
- acceso correcto a panel staff y panel admin;
- bloqueos por evento y verificaciones de permisos API;
- sistema visual y templates base;
- operaciones integradas de recarga, compra, descuento de saldo y entrega por QR.

La documentacion `01_Revision_Codigo_Django.pdf` agrega evidencia de una revision tecnica donde se identificaron y corrigieron riesgos criticos, en particular acceso indebido a rutas administrativas y advertencias de seguridad de despliegue. En esa misma revision se reporta que se agregaron pruebas de regresion para garantizar que un usuario autenticado no superusuario ya no pueda ingresar al panel administrativo.

En paralelo, se realizaron pruebas UX con usuarios invitados simulados para tres flujos clave:

- Cliente: consulta de menu, agregado al carrito y compra completa.
- Vendedor: edicion de tienda, alta de producto inventariable y desactivacion de producto.
- Staff: busqueda de usuario, sincronizacion de roles y asignacion de vendedor a puesto o espacio.

Los resultados fueron positivos en terminos de comprension y cierre de tareas. Las observaciones de mejora se concentraron en reforzar jerarquia visual del saldo, confirmaciones mas claras en acciones destructivas, mensajes de validacion menos saturados y diferenciacion mas notoria entre mensajes de exito y advertencia. Estas observaciones son utiles porque no invalidan el flujo principal, sino que orientan refinamientos de interfaz para siguientes iteraciones.

En conjunto, las pruebas respaldan que UPBCash ya cuenta con una base funcional verificable: el sistema controla acceso, procesa compras, descuenta stock, gestiona saldos, registra trazabilidad y ofrece una interfaz entendible para los usuarios previstos dentro del contexto de eventos escolares.

---

## Fuentes de respaldo usadas para este reporte

- Plantilla base: `/home/cchaires/Downloads/Proyecto Integrador_Reporte Final_2026-I.pdf`
- Resumen ejecutivo: `/home/cchaires/Downloads/Resumen Ejecutivo FEBRERO.docx.pdf`
- Reporte de avances: `/home/cchaires/Downloads/Reporte de avances AV.docx.pdf`
- Estado actual del proyecto: `Proyecto UPBCASH/upbcash_django/README.md`
- Gap list de migracion: `Proyecto UPBCASH/upbcash_django/MIGRACION_GAPS.md`
- Revision tecnica: `Proyecto UPBCASH/Documentacion/01_Revision_Codigo_Django.pdf`
- Pruebas automatizadas: `Proyecto UPBCASH/Documentacion/02_Pruebas_Automatizadas_Django.pdf`
- Evidencia UX: `Proyecto UPBCASH/Documentacion/03_Reporte_UX_Usuario_Invitado_1.pdf`
- Evidencia UX: `Proyecto UPBCASH/Documentacion/04_Reporte_UX_Usuario_Invitado_2.pdf`
- Evidencia UX: `Proyecto UPBCASH/Documentacion/05_Reporte_UX_Usuario_Invitado_3.pdf`
- Conceptualizacion UX: `Proyecto UPBCASH/Documentacion/USER PERSONA, WIREFRAMES, MOCKUPS e IA.pdf`
- Validacion operativa actual del repositorio: `DB_ENGINE=sqlite ./venv/bin/python manage.py test --verbosity 1` con `48 tests, OK`, y `./venv/bin/python manage.py check --deploy` sin incidencias de despliegue.

## Observacion de trazabilidad

Este reporte se redacto con base en el estado actual del repositorio y en la evidencia documental disponible. No se agregaron metricas de rendimiento ni resultados de pruebas no sustentados. La evidencia historica de `44 pruebas, OK` se conserva como respaldo documental de una iteracion previa, y adicionalmente ya se comprobo localmente el estado actual del proyecto con el entorno `venv`, donde la suite ejecuto `48 tests, OK` y `manage.py check --deploy` no reporto incidencias.
