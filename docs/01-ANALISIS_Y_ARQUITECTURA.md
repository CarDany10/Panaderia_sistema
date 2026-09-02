# Sistema de Administración para Panadería — Análisis y Arquitectura

**Estado:** Fase 1–3 aprobadas por el cliente (Análisis de requerimientos, Arquitectura técnica, Diseño de base de datos). Webflow confirmado como interfaz de todo el sistema.
**Siguiente:** Fase 4 (Configuración del proyecto Django + DRF).

---

## 1. RESUMEN EJECUTIVO DE LA DECISIÓN

| Pregunta | Decisión | Resumen |
|---|---|---|
| ¿Odoo o Django como núcleo? | **Django + DRF + PostgreSQL** (Opción C, con Odoo como integración opcional futura, no como núcleo) | Odoo no cubre con precisión las reglas de negocio exactas que pides (lb/oz, mermas, paquetes, visibilidad por rol muy granular) sin una capa de personalización tan grande que termina siendo, en la práctica, reescribir un backend a medida dentro de Odoo. Además Namecheap no ofrece el entorno de servidor que Odoo necesita. |
| ¿Webflow como interfaz completa del sistema? | **Sí — decisión confirmada por el cliente.** Webflow será la interfaz para TODO el sistema (panel interno de Admin/Trabajador/Repartidor y cara pública de Cliente), consumiendo 100% vía API DRF. | Se acepta el riesgo señalado (Webflow no valida nada en servidor): la contrapartida obligatoria es que Django **nunca envíe al navegador un dato que el rol no debe ver**, ni siquiera oculto por CSS/JS — ver sección 3.5 (actualizada) y sección 4. |
| ¿Google Calendar? | **Sí**, vía API oficial, con credenciales server-side (nunca en el frontend). | Encaja de forma limpia como servicio adicional del backend Django. |
| ¿Namecheap soporta todo esto? | **Parcial.** Django/PostgreSQL sí (con matices). Odoo no. | Ver sección 10. |

Esta decisión se explica en detalle en la sección 3. Nada de esto es código todavía — es la arquitectura que pides validar antes de programar.

---

## 2. ANÁLISIS DE REQUERIMIENTOS (FASE 1)

### 2.1 Dominios funcionales identificados
1. **Materia prima**: catálogo, compras (lotes), conversión lb↔oz, stock mínimo, alertas.
2. **Inventario de materia prima**: movimientos (entrada/salida/merma/ajuste), trazabilidad total.
3. **Producción**: consumo de materia prima, cantidad producida, merma, costo.
4. **Producto terminado**: inventario independiente, alimentado automáticamente por producción.
5. **Ventas**: unidad y por paquete, descuento automático de inventario, bloqueo de sobreventa.
6. **Pedidos de clientes**: flujo de estados, asignación a repartidor.
7. **Repartidores**: entregas, calificación 1–5 estrellas, historial.
8. **Clientes**: catálogo público, carrito, pedidos, calificación.
9. **Costos**: costo de compra → costo de producción → costo unitario de producto terminado, con trazabilidad, sin inventar porcentajes.
10. **Historial/auditoría**: bitácora única y filtrable (no reportes separados).
11. **Notificaciones**: stock bajo, pedidos, producción, eventos.
12. **Calendario**: eventos de producción y de entregas/pedidos vía Google Calendar.
13. **Usuarios y permisos**: 4 roles funcionales (Administrador, Trabajador de producción, Repartidor, Cliente), con administradores adicionales autorizables.
14. **Dashboards** diferenciados por rol.

### 2.2 Contradicciones / puntos que requieren definición explícita

Estas son cosas que el prompt no especifica y que **no voy a inventar** (regla #36). Necesito que las definas antes o durante la Fase 5–9, o bien acepto un valor por defecto marcado explícitamente como *configurable después*:

1. **Métodos de pago**: dices "si posteriormente se implementa". Para la Fase 9 dejaré el campo `metodo_pago` como texto/opcional sin lógica de cobro real (no hay pasarela de pago definida). Confirmar si se requiere pasarela (Stripe, tarjeta local, efectivo contra entrega, etc.) más adelante.
2. **Asignación de repartidor**: no se especifica si es manual (el administrador elige) o automática (por disponibilidad/zona). **Asumo manual** por el administrador, configurable después.
3. **Ajustes de inventario no autorizados**: dices que "no debe permitirse que una cantidad desaparezca sin registrar el motivo" y que un ajuste requiere autorización. Definiré un modelo `MovimientoInventario` con campo obligatorio de motivo y un flag de quién autorizó, pero el *flujo de aprobación* (¿el propio admin ajusta directamente, o un trabajador solicita y el admin aprueba?) lo dejo como: **el ajuste solo lo puede crear un Administrador** (el trabajador no tiene ese permiso). Si necesitas un flujo de solicitud/aprobación, es una fase posterior.
4. **Recetas/fórmulas**: dices "si el sistema las utiliza". El prompt de producción (sección 14) no pide una receta estructurada (materia prima × cantidad por unidad producida) sino que el trabajador **registra manualmente** la materia prima consumida en cada producción. **Decisión**: NO implementar un motor de recetas automático en el MVP (no se especificaron fórmulas ni proporciones, y la regla #36 prohíbe inventar porcentajes). El modelo de Producto tendrá un campo opcional para notas de receta, pero el consumo de materia prima en cada producción se **captura manualmente** por el trabajador en cada evento de producción. Si más adelante quieres recetas estandarizadas con auto-cálculo de consumo, es una fase adicional explícita.
5. **Unidades de medida de producto terminado**: la materia prima usa lb/oz. El producto terminado (panes, unidades) usa "unidades" y "paquetes". Confirmo que son sistemas de unidades independientes (correcto según tus ejemplos).
6. **Precio de venta**: no se especifica cómo se define el precio unitario de venta (¿manual por el admin, o fijo por producto?). **Asumo**: precio de venta configurable por producto (y por paquete), editable por el Administrador, independiente del costo (el costo es para análisis interno, el precio lo decide el negocio).
7. **Múltiples direcciones/zonas de entrega**: no se detalla. Se registrará una dirección de entrega por pedido (texto estructurado: dirección, referencia, teléfono), sin catálogo de zonas por ahora.
8. **Odoo**: si decides en algún momento sí quieres Odoo como sistema contable/fiscal aparte (facturación legal, contabilidad formal), esto se puede conectar como integración de **salida** (Django empuja ventas/compras a Odoo vía su API XML-RPC/JSON-RPC para contabilidad), sin que Odoo sea el núcleo operativo. Ver sección 3.4.

Si alguno de estos supuestos no es correcto, dímelo antes de Fase 4 y lo ajusto sin costo de rediseño mayor (están aislados por diseño).

---

## 3. EVALUACIÓN DE ARQUITECTURA (FASE 2)

### 3.1 Opción B — Odoo como núcleo completo

**A favor:**
- Odoo trae de fábrica Inventario, Compras, Manufactura (MRP), Ventas, Punto de Venta, Contactos/CRM, y una capa de permisos (grupos/reglas de acceso a nivel de registro).
- Ahorra tiempo si las reglas de negocio fueran genéricas.

**En contra (decisivo):**
- **Modelo de datos rígido para tus reglas específicas**: tu sistema exige lb↔oz con conversión exacta, venta por paquete con conversión a unidades, prohibición explícita de "costo promedio inventado" (Odoo por defecto usa costeo FIFO/promedio automático en su módulo de inventario — desactivarlo y forzar "costo manual por lote" tal como lo pides requiere modificar el core de `stock.valuation` vía código Python custom, no configuración).
- **Permisos por campo, no solo por modelo**: necesitas que un Trabajador vea "cantidad a producir" pero NUNCA "valor de inventario" del mismo registro de materia prima. Odoo protege por modelo/registro (grupos y reglas), no oculta campos específicos dentro de la misma vista sin crear vistas y reglas de campo personalizadas — de nuevo, esto es desarrollo de módulo Odoo (Python + XML), no configuración low-code.
- **Calificación de repartidores 1–5, estados de pedido a medida, dashboards por rol**: no existen en Odoo estándar; se construyen como módulo custom.
- **Conclusión**: para cubrir tus reglas *tal como las describes*, terminarías escribiendo un **módulo Odoo a medida** del mismo tamaño que una app Django — pero con la curva de aprendizaje adicional del ORM y ciclo de vida de Odoo, y con una comunidad/librerías menos alineadas a integraciones REST modernas y a Namecheap.
- **Hosting**: Odoo requiere un proceso de servidor de larga duración (`odoo-bin`), acceso típicamente root/VPS, workers, cron propio, y PostgreSQL con extensiones específicas. El hosting compartido de Namecheap (cPanel) **no soporta esto**; se necesitaría un VPS (Namecheap sí vende VPS, pero es una categoría de producto distinta a "hosting" que mencionas, con más costo y administración). Esto es una limitación real declarada explícitamente (regla #33).

**Veredicto: Opción B descartada** para el núcleo operativo.

### 3.2 Opción A — Webflow → Django API → PostgreSQL ↔ Odoo

Aquí la pregunta es si Django y Odoo pueden **coexistir**, no si Odoo reemplaza a Django.

- **Sí pueden coexistir**, pero solo tiene sentido si Odoo aporta algo que Django no: normalmente eso es **contabilidad formal/fiscal** (libros contables, declaraciones, facturación timbrada según el país). Si la panadería necesita eventualmente facturación fiscal formal, Odoo Contabilidad es una opción válida **como sistema satélite**, alimentado por Django vía su API (XML-RPC/JSON-RPC), no al revés.
- Para el MVP que describes (inventario, producción, ventas, pedidos, repartidores, costos operativos), **no hay ninguna necesidad funcional que Odoo resuelva mejor que Django+PostgreSQL**, y sí hay fricción de mantenimiento (dos sistemas, dos bases de datos, sincronización, dos lenguajes de configuración de permisos).
- **Conclusión**: la integración Odoo se **pospone** y se deja como *punto de extensión* (Fase 14 sigue existiendo pero como "integración contable opcional", no como dependencia del sistema operativo diario).

### 3.3 Opción C — Webflow → Django REST Framework → PostgreSQL

**Esta es la base de la arquitectura recomendada**, con un matiz importante en la capa de frontend (sección 3.5).

Ventajas:
- Control total y exacto sobre las reglas de negocio (conversión lb/oz, costeo manual, visibilidad por campo y rol, estados de pedido, calificaciones) sin pelear contra un ORM/UI ajeno.
- Django admin + DRF dan velocidad de desarrollo real para un sistema interno.
- Despliegue compatible con hosting compartido/Python de Namecheap (Passenger/WSGI) sin necesitar VPS.
- Un solo lenguaje (Python) y una sola base de datos (PostgreSQL) para todo el núcleo — menos superficie de fallo, más fácil de auditar y asegurar.

### 3.4 Rol de Odoo en esta arquitectura (definitivo)

**No forma parte del MVP.** Se documenta como integración futura opcional:
Django (fuente de verdad operativa) → API de Odoo (XML-RPC) → Odoo Contabilidad (solo si más adelante se requiere facturación fiscal formal). Esto es Fase 14, y es "puede omitirse sin romper nada" — el sistema es 100% funcional sin ella.

### 3.5 Rol de Webflow (DECISIÓN CONFIRMADA: Webflow para todo el sistema)

Se planteó como hallazgo de riesgo y el cliente confirmó explícitamente: **Webflow será la interfaz de TODO el sistema**, incluyendo el panel interno de Administrador, Trabajador de producción y Repartidor, no solo la cara pública del Cliente. Se acepta.

Esto cambia el rol de Django: **Django deja de servir cualquier HTML/template propio para el uso diario del sistema** (salvo el Django Admin, que se mantiene solo como panel técnico de emergencia para el desarrollador, no para los usuarios finales). Django pasa a ser **100% un backend API (DRF)**, y Webflow consume esa API para las 4 vistas por rol.

**Implicación de seguridad que se vuelve innegociable** (y que ya estaba en la regla #30, pero ahora es la única línea de defensa): Webflow, al ser una herramienta de maquetación que compila a HTML/CSS/JS estático servido al navegador, **no puede validar ni ocultar nada del lado servidor**. Cualquier persona puede abrir las herramientas de desarrollador del navegador e inspeccionar cada respuesta JSON que Django envía. Por lo tanto:

- **Nunca se envía al navegador un campo que el rol no deba ver**, ni siquiera para "ocultarlo con CSS". Ejemplo: si un Trabajador consulta materia prima, el JSON que Django le entrega **no contiene** `costo_unitario` ni `valor_inventario` en absoluto — no es que el campo llegue y Webflow lo oculte. Esto se logra con **serializers de DRF distintos por rol** (ver sección 4), nunca con un serializer único "completo" filtrado en el cliente.
- El "menú por rol" (sección 35 del prompt) en Webflow es solo una conveniencia de UX (mostrar/ocultar enlaces según el rol leído del token); la protección real es que, aunque un Trabajador edite el HTML/JS de su navegador e intente llamar directamente a `/api/v1/materia-prima/valor-inventario/`, el backend responde `403` porque valida `request.user.rol` en cada endpoint, siempre.
- Rutas de Webflow por rol: cada rol tiene sus propias páginas Webflow (p. ej. `/panel/admin/...`, `/panel/produccion/...`, `/panel/reparto/...`, `/panel/cliente/...`). Al cargar cualquiera de esas páginas, un script de guardia (compartido entre páginas) valida el rol contenido en el JWT vigente y redirige si no coincide — esto es solo UX, la seguridad real vive en el backend como se explicó arriba.

**Cómo se construye técnicamente el panel dentro de Webflow:**
- Cada pantalla del sistema (Dashboard, Materia Prima, Producción, Ventas, Pedidos, Historial, etc.) es una página de Webflow con los contenedores/tablas/formularios maquetados visualmente.
- Un conjunto de módulos de JavaScript (vanilla JS, cargados vía `<script>` en el Embed/Custom Code de Webflow, o alojados como archivos estáticos versionados aparte) se encargan de: autenticar, leer el rol, pedir datos a la API, pintar tablas dinámicas, manejar formularios y validaciones, y mostrar errores/confirmaciones — enlazados a los elementos de Webflow mediante atributos `id`/`data-*`.
- Esto es más artesanal que un framework de frontend (React/Vue) y requiere disciplina para no duplicar lógica entre páginas, pero es viable y es la única forma de lograr "todo en Webflow" sin sacrificar la separación de responsabilidades pedida en la sección 5 del prompt (Webflow nunca toca la base de datos directamente).

**Se retira, por tanto, el uso de Django templates.** Django Admin queda solo como herramienta interna de soporte técnico (no como parte del producto que usan los 4 roles).

### 3.6 Diagrama de arquitectura definitiva

```
┌──────────────────────────────────────────────────────────────────┐
│                          WEBFLOW (todo el frontend)                 │
│  Páginas por rol + JS custom (fetch a la API, guardias de rol UX)    │
│  Admin | Trabajador | Repartidor | Cliente                          │
└───────────────────────────────┬────────────────────────────────────┘
                                 │ HTTPS / REST (JWT access en memoria +
                                 │ refresh en cookie HttpOnly, mismo dominio raíz)
                                 ▼
┌───────────────────────────────────────────────────────────────────┐
│                    DJANGO (100% API — sin templates de producto)     │
│  ┌───────────────┐   ┌───────────────────────────────────────┐      │
│  │ Django Admin   │   │ Django REST Framework                  │      │
│  │ (solo soporte  │   │ Serializers DISTINTOS por rol           │      │
│  │  técnico dev)  │   │ Permisos validados en CADA endpoint     │      │
│  └───────────────┘   └───────────────────────────────────────┘      │
│                                   │                                  │
│                                   ▼                                  │
│              Capa de permisos y reglas de negocio                    │
│              (servicios / lógica de dominio)                         │
└──────────────────────┬───────────────────────────────────────────┘
                        │
          ┌─────────────┼───────────────────┐
          ▼             ▼                   ▼
   ┌─────────────┐ ┌────────────┐   ┌──────────────────┐
   │ PostgreSQL   │ │ Google     │   │ Odoo (futuro,     │
   │ (única DB)   │ │ Calendar   │   │ opcional, solo    │
   │              │ │ API        │   │ contabilidad)      │
   └─────────────┘ └────────────┘   └──────────────────┘
```

### 3.7 Responsabilidad de cada tecnología

| Componente | Responsabilidad |
|---|---|
| **PostgreSQL** | Única fuente de verdad de datos. |
| **Django (ORM + lógica de dominio)** | Reglas de negocio: conversión lb/oz, costeo, control de stock negativo, estados de pedido, permisos por campo. |
| **Django REST Framework** | **Única** interfaz del sistema hacia el exterior: endpoints JSON para las 4 vistas de Webflow (Admin, Trabajador, Repartidor, Cliente) y, a futuro, app móvil. Cada endpoint decide qué campos entrega según `request.user.rol`. |
| **Django Admin** | Panel técnico interno solo para soporte/depuración del desarrollador — no forma parte del producto que usan los 4 roles. |
| **Webflow** | Interfaz visual completa del sistema (panel interno + cara pública), 100% vía llamadas a la API. Nunca accede a la base de datos directamente. |
| **Google Calendar API** | Servicio adicional invocado por Django al crear/editar producción o entrega. |
| **Odoo (futuro opcional)** | Contabilidad/fiscalidad formal, alimentada por Django. No es requerido para operar. |

---

## 4. AUTENTICACIÓN Y AUTORIZACIÓN

Como Webflow consume la API desde un origen distinto hacia `api.<tu-dominio>` (Django), el esquema de autenticación es **100% basado en tokens**, sin sesiones de Django ni formularios server-rendered:

- **Autenticación**: Django's `django.contrib.auth` (hash de contraseñas Argon2) + **JWT (SimpleJWT)**.
  - **Access token**: de vida corta (10–15 min), se mantiene **en memoria de JavaScript** en la página de Webflow (nunca en `localStorage`, para reducir exposición ante un XSS).
  - **Refresh token**: en **cookie HttpOnly + Secure + SameSite=Lax**, emitida por `api.<tu-dominio>`. Esto funciona sin fricción de CORS/SameSite si Webflow y la API se publican bajo el **mismo dominio raíz** (p. ej. `www.tupanaderia.com` para Webflow y `api.tupanaderia.com` para Django) — son "same-site" para el navegador aunque sean orígenes distintos, así que la cookie de refresh viaja automáticamente. **Esto es un requisito de dominio, no solo de configuración**: hay que apuntar el subdominio `api.` de tu dominio a Namecheap/Django desde el inicio.
  - Si Webflow se publicara en un dominio *distinto* al de la API (p. ej. un subdominio gratuito tipo `algo.webflow.io`), el refresh en cookie deja de ser seguro entre sitios — por eso se recomienda dominio propio para ambos desde el día uno.
- **Autorización por rol**: modelo `Usuario` (extiende `AbstractUser`) con campo `rol` (`ADMIN`, `TRABAJADOR`, `REPARTIDOR`, `CLIENTE`). Los administradores adicionales son simplemente usuarios con `rol=ADMIN`, creados por un Administrador existente (nunca autoregistro para ese rol).
- **Autorización por campo** (crítico, regla #7/#30, y ahora la única línea de defensa real dado que Webflow no valida nada en servidor): se implementa con **serializers de DRF distintos por rol** — el JSON que sale de Django hacia un Trabajador **físicamente no contiene** los campos financieros; no es que lleguen y se oculten en la interfaz. Cada endpoint valida `request.user.rol` en el backend antes de construir la respuesta.
- **Permisos técnicos**: clases `permissions.BasePermission` custom por rol (`EsAdministrador`, `EsTrabajador`, `EsRepartidor`, `EsCliente`, más `EsPropietarioDelPedido` para que un repartidor solo vea sus entregas y un cliente solo sus pedidos).
- **CORS**: `django-cors-headers` restringido explícitamente a los dominios de Webflow usados (producción y, si aplica, staging), con `CORS_ALLOW_CREDENTIALS=True` para permitir el envío de la cookie de refresh.
- **Auditoría de acceso indebido** (regla #40): pruebas automatizadas que golpean cada endpoint sensible con cada rol y verifican 403/campo ausente en la respuesta JSON — no solo que la UI no lo muestre.

---

## 5. DISEÑO DE BASE DE DATOS (FASE 3)

### 5.1 Principios de diseño
- Cada movimiento (compra, consumo, merma, ajuste, venta) es un **registro inmutable** (append-only) — nunca se recalculan existencias reescribiendo un campo sin dejar rastro del movimiento que lo originó.
- La "existencia actual" de materia prima y de producto terminado se calcula como un campo cacheado en el modelo principal, pero **siempre reconstruible** sumando sus movimientos — el movimiento es la fuente de verdad, el campo cacheado es una optimización de lectura.
- Todo modelo transaccional tiene `creado_por`, `creado_en`, y donde aplique `motivo`.

### 5.2 Entidades principales y relaciones

```
Usuario (AbstractUser + rol)
 ├─ PerfilTrabajador (1:1, opcional)
 ├─ PerfilRepartidor (1:1, opcional) ── calificacion_promedio (calculado)
 └─ PerfilCliente (1:1, opcional)

MateriaPrima
 ├─ id, nombre, descripcion, unidad_medida (LB|OZ), stock_actual, stock_minimo, estado
 └─ Compra (FK MateriaPrima)          [lote, cantidad, unidad, costo_total, costo_unitario, fecha]
      └─ genera → MovimientoInventarioMateriaPrima (tipo=COMPRA, +cantidad)

MovimientoInventarioMateriaPrima
 ├─ materia_prima FK, tipo (COMPRA|PRODUCCION|MERMA|AJUSTE), cantidad (+/-),
 │   unidad_medida, motivo, referencia (FK genérica a Compra/Produccion/Ajuste),
 │   saldo_resultante, creado_por, creado_en

Producto  (producto terminado, ej. "Pan Francés")
 ├─ id, nombre, descripcion, precio_unitario, unidad_venta_base
 └─ Paquete (FK Producto)             [nombre, unidades_por_paquete, precio_paquete]

Produccion
 ├─ numero, producto FK, fecha, cantidad_planificada, cantidad_producida,
 │   cantidad_merma, costo_total, costo_unitario (calculado = costo_total/cantidad_producida)
 ├─ ConsumoMateriaPrima (FK Produccion, FK MateriaPrima) [cantidad, unidad, costo_correspondiente]
 │     └─ genera → MovimientoInventarioMateriaPrima (tipo=PRODUCCION, -cantidad)
 └─ genera → MovimientoInventarioProductoTerminado (tipo=PRODUCCION, +cantidad_producida)
 └─ (si cantidad_merma > 0) → MovimientoInventarioProductoTerminado (tipo=MERMA, -cantidad_merma)

ProductoTerminadoStock (o campo stock_actual en Producto)
 └─ MovimientoInventarioProductoTerminado
     [producto FK, tipo (PRODUCCION|VENTA|MERMA|AJUSTE), cantidad (+/-), referencia, creado_por, creado_en]

Venta
 ├─ numero, fecha, cliente FK (nullable si venta de mostrador), estado, metodo_pago (opcional)
 └─ DetalleVenta (FK Venta) [producto FK, paquete FK (nullable), cantidad, precio_unitario, subtotal]
     └─ genera → MovimientoInventarioProductoTerminado (tipo=VENTA, -cantidad_en_unidades)

Pedido
 ├─ numero, cliente FK, fecha, estado (PENDIENTE|EN_PREPARACION|EN_CAMINO|ENTREGADO|CANCELADO),
 │   direccion_entrega, telefono_contacto, repartidor FK (nullable hasta asignación)
 ├─ DetallePedido (FK Pedido) [producto FK, paquete FK (nullable), cantidad, precio_unitario]
 └─ Entrega (1:1 Pedido) [repartidor FK, fecha_asignacion, fecha_entrega, estado]
      └─ Calificacion (1:1 Entrega) [estrellas 1-5, comentario opcional, fecha, cliente FK, repartidor FK]

EventoCalendario
 [tipo (PRODUCCION|PEDIDO), referencia_id, google_event_id, titulo, fecha_inicio, fecha_fin, creado_por]

Notificacion
 [destinatario FK Usuario, tipo, titulo, mensaje, leida, creado_en, referencia_id opcional]

RegistroAuditoria (bitácora / "HISTORIAL")
 [tipo_operacion, entidad, entidad_id, usuario FK, descripcion, datos_previos (JSON), datos_nuevos (JSON), creado_en]
```

### 5.3 Notas de diseño relevantes a tus reglas
- **Conversión lb/oz**: `MateriaPrima.unidad_medida` define la unidad "nativa" de esa materia prima; todo movimiento se guarda en su unidad nativa, con un método de dominio `convertir(cantidad, de, a)` (1 lb = 16 oz) usado solo para *mostrar/mezclar* unidades al capturar una compra en una unidad distinta a la nativa. Nunca se pierde precisión (se usa `Decimal`, no `float`).
- **Costo unitario manual, nunca promedio automático inventado** (regla #11/#36): `Compra.costo_unitario` se calcula por defecto como `costo_total / cantidad` **de esa compra específica**, pero el campo es editable manualmente antes de guardar. El consumo en producción (`ConsumoMateriaPrima.costo_correspondiente`) se captura contra el lote/compra específico que el trabajador indique (o el más antiguo disponible, FIFO, si no se especifica) — nunca un promedio ponderado histórico salvo que tú pidas explícitamente esa regla.
- **Bloqueo de sobreventa/sobreconsumo** (regla #12/#38): a nivel de servicio de dominio (transacción atómica con `select_for_update`), cualquier intento de generar un `MovimientoInventario...` que deje `stock_actual < 0` es rechazado con error explícito, salvo un `AjusteAutorizado` creado únicamente por un Administrador.
- **"HISTORIAL" único**: `RegistroAuditoria` es una tabla, pero además la vista de Historial hace UNION filtrable sobre los movimientos reales (Compra, Producción, Merma, Venta, Pedido, Ajuste) para no perder detalle — la bitácora resume "qué pasó", los movimientos originales siguen siendo la fuente de verdad de cada dominio.

---

## 6. ROLES Y PERMISOS (RESUMEN)

| Módulo | Admin | Trabajador | Repartidor | Cliente |
|---|:---:|:---:|:---:|:---:|
| Ver stock de materia prima (cantidad) | ✅ | ✅ (solo para saber si alcanza) | ❌ | ❌ |
| Ver **valor** de materia prima | ✅ | ❌ | ❌ | ❌ |
| Registrar compra | ✅ | ❌ | ❌ | ❌ |
| Registrar producción/consumo/merma | ✅ | ✅ | ❌ | ❌ |
| Ver costos e ingresos | ✅ | ❌ | ❌ | ❌ |
| Ver producto terminado (cantidad) | ✅ | ✅ | ❌ | ✅ (solo disponible para venta) |
| Registrar venta | ✅ | ❌ | ❌ | ❌ (el cliente "compra" vía Pedido) |
| Crear pedido | — | — | ❌ | ✅ |
| Asignar repartidor | ✅ | ❌ | ❌ | ❌ |
| Actualizar estado de entrega | ✅ | ❌ | ✅ (solo sus pedidos) | ❌ |
| Calificar repartidor | ❌ | ❌ | ❌ | ✅ (solo su propio pedido entregado) |
| Ver historial completo | ✅ | ❌ (solo su propio registro de producciones) | ❌ (solo sus entregas) | ❌ (solo sus pedidos) |
| Gestionar usuarios/permisos | ✅ | ❌ | ❌ | ❌ |

---

## 7. ENDPOINTS PRINCIPALES (borrador, se detalla en Fase 5+)

Prefijo `/api/v1/`. Todos requieren autenticación salvo `catalogo/` de solo lectura.

- `auth/` login, refresh, logout
- `usuarios/` (Admin) CRUD, `usuarios/{id}/hacer-admin/`
- `materia-prima/` CRUD (Admin), lectura restringida a cantidad para Trabajador
- `compras/` (Admin) crear/listar
- `movimientos-materia-prima/` (Admin: todo; Trabajador: solo lectura sin costo)
- `producciones/` crear/listar (Admin+Trabajador)
- `producto-terminado/` lectura (todos los roles, campos filtrados)
- `ventas/` crear/listar (Admin)
- `pedidos/` crear (Cliente), listar propios (Cliente), listar todos (Admin), asignar repartidor (Admin), actualizar estado (Repartidor propio)
- `entregas/mis-entregas/` (Repartidor)
- `calificaciones/` crear (Cliente, solo tras entrega), consultar promedio (todos)
- `calendario/eventos/` CRUD (Admin)
- `notificaciones/` listar propias, marcar leída
- `historial/` (Admin) filtrable por fecha/tipo/entidad
- `dashboard/` resumen según rol del usuario autenticado

---

## 8. SEGURIDAD

- HTTPS obligatorio (Let's Encrypt vía cPanel de Namecheap o proxy).
- Contraseñas con hashing fuerte (Argon2 vía `django-argon2`).
- Sin sesiones/CSRF de Django para el producto (todo es API stateless con JWT); CORS restringido a los dominios de Webflow conocidos; cookie de refresh HttpOnly+Secure+SameSite.
- Rate limiting en login y endpoints públicos (`django-ratelimit`), especialmente relevante al no haber CSRF de por medio.
- Validación de permisos en **cada** vista/endpoint (nunca solo en frontend) — cubierto por pruebas automatizadas (Fase 15/40).
- Variables de entorno (`.env`, nunca en el repositorio) para: `SECRET_KEY`, credenciales de PostgreSQL, credenciales de Google Calendar (`client_secret.json`/token), y futura credencial de Odoo.
- Registro de operaciones sensibles en `RegistroAuditoria` (quién, qué, cuándo, valores previos/nuevos).

---

## 9. HISTORIAL DE NAMECHEAP — COMPATIBILIDAD (FASE 33, adelantado)

| Requisito | ¿Namecheap shared hosting lo da? | Nota |
|---|---|---|
| Python/Django (WSGI vía Passenger) | ✅ (planes con soporte "Python App" en cPanel) | Confirmar plan específico contratado antes de Fase 16. |
| PostgreSQL | ⚠️ Depende del plan — muchos planes compartidos de Namecheap **solo ofrecen MySQL**, PostgreSQL suele requerir plan superior o VPS. | **Riesgo real a resolver antes de Fase 16**: si el plan contratado no da PostgreSQL, alternativas mínimas: (a) usar un PostgreSQL gestionado externo (p.ej. un proveedor con free/low-cost tier) mientras el resto vive en Namecheap, o (b) subir de plan/VPS en Namecheap. **No se sacrificará el modelo relacional ni se cambiará a MySQL sin tu aprobación explícita**, tal como pide la regla #33. |
| Procesos de fondo (cron para notificaciones/alertas) | ✅ vía cron jobs de cPanel | Usable para tareas periódicas (revisar stock mínimo, etc.) |
| HTTPS/SSL | ✅ (AutoSSL/Let's Encrypt incluido en cPanel) | |
| Dominio/subdominios | ✅ | Subdominio dedicado para la API si se separa del panel. |
| Odoo | ❌ en shared hosting | Requeriría VPS — pospuesto, ver sección 3.4. |
| Google Calendar API | ✅ (solo llamadas HTTPS salientes) | Sin requisitos especiales de servidor. |

**Acción pendiente de tu parte**: confirmar el plan de Namecheap contratado (o que planeas contratar) para verificar disponibilidad real de PostgreSQL antes de Fase 16. Si no está disponible, lo resolvemos entonces sin tocar el diseño (solo el proveedor de la base de datos).

---

## 10. FASES DE DESARROLLO (confirmación del plan pedido)

Se sigue el plan de 16 fases que definiste (sección 39 del prompt). Fase 14 (Odoo) queda como integración opcional post-lanzamiento. **Fase 13 (Webflow) ahora cubre el diseño completo del sistema** (panel interno + cara pública), no solo la parte pública, conforme a tu decisión. Cada fase se entrega con sus propias pruebas antes de continuar (regla #39/#40).

---

## 11. RIESGOS Y LIMITACIONES DECLARADOS

1. **Webflow para todo el panel interno — decisión confirmada.** Riesgo aceptado: no hay validación de servidor en la capa visual, por lo que **toda** la seguridad recae en Django/DRF (serializers por rol, permisos en cada endpoint). Cualquier fuga de datos financieros a un rol no autorizado sería un defecto del backend, no del frontend — así se diseñarán y probarán los serializers (Fase 5 en adelante).
2. **Requisito de dominio propio compartido** entre Webflow y la API (`www.tudominio.com` + `api.tudominio.com`) para que la autenticación por cookie de refresh sea segura y sin fricciones de CORS — ver sección 4. Si aún no tienes el dominio configurado así, es una tarea previa a Fase 16 (y conviene resolverla antes, para probar la autenticación real en Fase 5).
3. **PostgreSQL en Namecheap shared hosting no está garantizado** en todos los planes — ver sección 9. Sigue pendiente de tu confirmación (punto 3 de tu respuesta: "no poseo esa información"). No bloquea el desarrollo (Fases 4–15 se pueden construir y probar localmente/en cualquier PostgreSQL), pero sí debe resolverse antes de Fase 16 (despliegue). Cuando tengas o elijas el plan de Namecheap, lo verificamos.
4. **No hay motor de recetas automático** en el MVP (no se especificaron proporciones) — el consumo de materia prima por producción se captura manualmente, tal como exige la regla #36. Mantengo este supuesto por defecto (tu respuesta fue "no sé"); es ajustable después sin romper el diseño si más adelante quieres recetas estandarizadas.
5. **Asignación manual de repartidor y precio de venta manual** (sección 2.2, puntos 2 y 6): se mantienen como supuestos por defecto configurables, ya que no indicaste lo contrario.
6. **No hay pasarela de pago real** definida — el campo existe pero sin lógica de cobro hasta que la definas.
7. **Odoo pospuesto**: si en algún momento decides que sí es indispensable como núcleo (no solo contabilidad), eso implica volver a evaluar el hosting (VPS) y una re-arquitectura parcial — se declara explícitamente para que la decisión sea informada.

---

## 12. SIGUIENTE PASO

Con el alcance de Webflow confirmado (todo el sistema) y los supuestos de la sección 2.2 mantenidos por defecto, se procede a **Fase 4 (Configuración del proyecto Django + DRF)**. Puntos que seguirán abiertos y no bloquean el arranque:
- Confirmar el plan de Namecheap y disponibilidad de PostgreSQL (antes de Fase 16).
- Contar con el dominio propio para configurar `www.` (Webflow) y `api.` (Django) antes de probar el flujo de autenticación real (Fase 5).
