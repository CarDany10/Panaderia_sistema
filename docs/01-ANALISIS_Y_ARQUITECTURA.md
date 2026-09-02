# Sistema de Administración para Panadería — Análisis y Arquitectura

**Estado:** Fase 1–3 (Análisis de requerimientos, Arquitectura técnica, Diseño de base de datos)
**Pendiente:** Aprobación del cliente antes de iniciar Fase 4 (código de implementación).

---

## 1. RESUMEN EJECUTIVO DE LA DECISIÓN

| Pregunta | Decisión | Resumen |
|---|---|---|
| ¿Odoo o Django como núcleo? | **Django + DRF + PostgreSQL** (Opción C, con Odoo como integración opcional futura, no como núcleo) | Odoo no cubre con precisión las reglas de negocio exactas que pides (lb/oz, mermas, paquetes, visibilidad por rol muy granular) sin una capa de personalización tan grande que termina siendo, en la práctica, reescribir un backend a medida dentro de Odoo. Además Namecheap no ofrece el entorno de servidor que Odoo necesita. |
| ¿Webflow como interfaz completa del sistema? | **No para el panel interno.** Sí como opción para páginas públicas/mercadeo. | Webflow es una herramienta de diseño de sitios, no un framework de aplicación con estado, tablas de datos dinámicas, RBAC por campo, ni SPA. Meter todo el ERP dentro de Webflow + API introduce fragilidad y no es lo que usan sistemas empresariales reales. Te explico la alternativa abajo (sección 8). |
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

### 3.5 Rol de Webflow (hallazgo importante — necesita tu decisión)

Pediste explícitamente que evalúe esto con honestidad, así que aquí está sin adornos:

**Webflow no es apto como interfaz completa de un ERP interno con 4 roles, tablas de datos dinámicas, formularios con validación cruzada de inventario, y RBAC a nivel de campo.** Webflow es una herramienta de diseño de sitios (CMS + maquetación visual) pensada para páginas de marketing, no para SPAs con estado complejo, tablas editables, ni protección de rutas por rol a nivel de UI granular. Puedes conectarlo a una API (como pides), pero para lograr un panel interno real terminarías escribiendo, a mano, con JavaScript personalizado dentro de Webflow, el equivalente a un framework de frontend — perdiendo justo la ventaja de "diseño visual sin código" que buscas en Webflow, y con mucha fragilidad para mantenimiento futuro.

**Recomendación (para tu aprobación):**
- **Panel interno** (Dashboard, Materia Prima, Producción, Ventas, Pedidos, Historial, etc., para Administrador/Trabajador/Repartidor): construir con **Django templates + Bootstrap 5 + JS moderno (vanilla o Alpine.js)**, sirviendo directamente desde el backend. Esto es lo que usan sistemas empresariales reales similares (más rápido, más seguro, permisos consistentes en una sola capa), y sigue tu paleta blanco/beige/café tal como la definiste.
- **Webflow** se reserva para lo que sí hace excelente: la **cara pública para el Cliente** (catálogo de productos, landing, "Iniciar sesión"/"Crear pedido") consumiendo la API de Django — esto es exactamente tu "Opción A" pero aplicada solo a la porción pública, no al ERP interno completo.
- Si prefieres insistir en Webflow para todo el sistema (incluyendo el panel del Administrador), lo puedo hacer, pero quiero que la decisión sea explícita tuya porque implica más riesgo de mantenimiento y peor cumplimiento de "seguridad en backend, no en frontend" (regla #30), ya que Webflow no valida nada en servidor.

**Necesito tu confirmación sobre este punto antes de Fase 13** (no bloquea Fases 4–12, que son 100% backend). Si no dices nada, procederé con la recomendación (Django templates para el panel interno, Webflow opcional para la cara pública del cliente).

### 3.6 Diagrama de arquitectura definitiva

```
                    ┌────────────────────────────┐
                    │   Webflow (opcional)        │
                    │   Catálogo público / login  │
                    │   SOLO para Cliente          │
                    └──────────────┬──────────────┘
                                   │ HTTPS / REST (JWT)
                                   ▼
┌───────────────────────────────────────────────────────────┐
│                     DJANGO (monolito modular)               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Django       │  │ Django REST  │  │ Panel interno     │   │
│  │ Admin (staff)│  │ Framework    │  │ (templates+JS)    │   │
│  │              │  │ (API pública/│  │ Admin/Trabajador/ │   │
│  │              │  │ móvil futuro)│  │ Repartidor         │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│         │                 │                   │             │
│         └────────────┬────┴───────────────────┘             │
│                       ▼                                     │
│              Capa de permisos y reglas de negocio            │
│              (servicios / lógica de dominio)                 │
└──────────────────────┬────────────────────────────────────┘
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
| **Django REST Framework** | Endpoints JSON para Webflow (catálogo público, pedidos de cliente) y para futura app móvil. |
| **Django templates + Bootstrap + JS** | Panel interno operativo (Admin, Trabajador, Repartidor). |
| **Webflow (opcional)** | Cara pública de marketing + catálogo + flujo de pedido del cliente, consumiendo la API. |
| **Google Calendar API** | Servicio adicional invocado por Django al crear/editar producción o entrega. |
| **Odoo (futuro opcional)** | Contabilidad/fiscalidad formal, alimentada por Django. No es requerido para operar. |

---

## 4. AUTENTICACIÓN Y AUTORIZACIÓN

- **Autenticación**: Django's `django.contrib.auth` (hash de contraseñas Argon2/PBKDF2), sesiones para el panel interno (cookies HttpOnly + CSRF), y **JWT (SimpleJWT)** para el consumo desde Webflow/API pública (clientes).
- **Autorización por rol**: modelo `Usuario` (extiende `AbstractUser`) con campo `rol` (`ADMIN`, `TRABAJADOR`, `REPARTIDOR`, `CLIENTE`). Los administradores adicionales son simplemente usuarios con `rol=ADMIN`, creados por un Administrador existente (nunca autoregistro para ese rol).
- **Autorización por campo** (crítico, regla #7/#30): se implementa con **serializers de DRF distintos por rol** y **querysets/`.only()`/exclusión de campos explícita** en las vistas — nunca se confía en ocultar botones en el HTML. Cada endpoint valida `request.user.rol` en el backend antes de construir la respuesta.
- **Permisos técnicos**: clases `permissions.BasePermission` custom por rol (`EsAdministrador`, `EsTrabajador`, `EsRepartidor`, `EsCliente`, más `EsPropietarioDelPedido` para que un repartidor solo vea sus entregas y un cliente solo sus pedidos).
- **Auditoría de acceso indebido** (regla #40): pruebas automatizadas que golpean cada endpoint sensible con cada rol y verifican 403/campo ausente.

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
- CSRF activo en panel interno; JWT + CORS restringido a dominios conocidos para la API pública/Webflow.
- Rate limiting en login y endpoints públicos (`django-ratelimit`).
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

Se sigue el plan de 16 fases que definiste (sección 39 del prompt), con la aclaración de que Fase 14 (Odoo) queda como integración opcional post-lanzamiento y Fase 13 (Webflow) se acota a la cara pública del cliente salvo que me indiques lo contrario. Cada fase se entrega con sus propias pruebas antes de continuar (regla #39/#40).

---

## 11. RIESGOS Y LIMITACIONES DECLARADOS

1. **Webflow no es apto para el panel interno completo** — ver sección 3.5. Necesito tu confirmación de alcance.
2. **PostgreSQL en Namecheap shared hosting no está garantizado** en todos los planes — ver sección 9.
3. **No hay motor de recetas automático** en el MVP (no se especificaron proporciones) — el consumo de materia prima por producción se captura manualmente, tal como exige la regla #36.
4. **No hay pasarela de pago real** definida — el campo existe pero sin lógica de cobro hasta que la definas.
5. **Odoo pospuesto**: si en algún momento decides que sí es indispensable como núcleo (no solo contabilidad), eso implica volver a evaluar el hosting (VPS) y una re-arquitectura parcial — se declara explícitamente para que la decisión sea informada.

---

## 12. SIGUIENTE PASO

Quedo a la espera de tu aprobación (o ajustes) sobre:
1. El alcance de Webflow (sección 3.5).
2. Los supuestos de la sección 2.2 (especialmente: recetas manuales, asignación manual de repartidor, precio de venta manual).
3. El plan de hosting de Namecheap contratado (para validar PostgreSQL).

Con eso confirmado, continúo con **Fase 4 (Configuración del proyecto Django)** y siguientes, sin generar código de negocio hasta ese punto.
