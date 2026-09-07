# Corrección del primer simulacro — 4 de septiembre de 2026

## Veredicto

Buena primera entrega: el flujo principal está completo, el código tiene límites
claros y la solución resuelve los casos centrales de los fixtures. No la daría por
cerrada todavía: hay un error importante de matching y tres problemas adicionales
de preservación o validación de datos.

Evaluación orientativa: **75/100, provisional**. Es una calificación de práctica,
no una predicción del criterio del evaluador. La defensa oral y el desempeño dentro de
90 minutos todavía no están evaluados.

| Dimensión | Puntos | Motivo |
|---|---:|---|
| Correctitud y calidad de datos | 22/30 | Casos centrales resueltos; ambigüedad prematura, pérdida de aliases y coerción numérica insegura. |
| Confiabilidad y diseño | 18/25 | Reruns determinísticos y separación de errores; conversión temporal puede abortar la ingesta; búsqueda de nombres no escala. |
| Calidad y testing | 16/20 | Módulos claros y tests útiles; pipeline probada principalmente con los mismos fixtures. |
| Comunicación y trade-offs | 11/15 | Documentación extensa y buenas preguntas; algunas políticas no coinciden con el código; defensa oral pendiente. |
| Uso de IA | 8/10 | Trabajo por etapas, ejecución de tests declarada por el usuario y cuestionamiento de restricciones inventadas; falta comprobar dominio oral de la resolución. |

## Evidencia ejecutada

- Suite existente: **56 passed in 3.41s**.
- Suite independiente: **5 passed, 6 failed in 2.20s**. Los seis fallos representan
  cuatro problemas distintos; no son seis bugs independientes ni una muestra
  estadística de calidad.
- Confirmado: reversión del orden de filas conserva el resultado de los fixtures.
- Confirmado: ejecución desde otro directorio y con PYTHONHASHSEED 1/42 produce
  outputs byte-idénticos.
- Confirmado: copias de un ID de interacción que resuelven a distintas compañías
  se rechazan; copias de una misma compañía cuentan una vez con la fecha más nueva.
- Confirmado: una observación market con fecha válida gana a otra sin fecha válida.
- La suite adicional está fuera del repositorio de la entrega. No modifiqué la
  solución, sus tests, la consigna ni los outputs entregados.

Para reproducir desde `outputs/data-platform-mock`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest ../review-2026-09-04/test_review.py -q -p no:cacheprovider --tb=short
```

## Hallazgos reproducidos

### 1. P1 — Se acepta un match por nombre antes de conocer todos los candidatos

Ubicación: `src/data_challenge/pipeline.py:233`, `_attach_market_records`.

La función procesa market por ID y resuelve inmediatamente cada fila. Con CRM
vacío y estos registros:

| ID | Nombre | Dominio |
|---|---|---|
| M1 | Beacon | a.example |
| M2 | Beacon | sin dominio |
| M3 | Beacon | b.example |

M2 se adjunta a a.example porque M3 todavía no fue procesado. En el batch completo
hay dos candidatos: M2 debe rechazarse como ambiguo. Si M2 tiene métricas más
recientes, puede contaminar el funding o el headcount de a.example.

Ordenar por ID hace reproducible la decisión, pero no la hace correcta. La
dirección de corrección es construir primero la evidencia fuerte e índices de
candidatos completos y resolver después los fallbacks por nombre. También hay
que revisar el enriquecimiento de una entidad CRM sin dominio cuando distintas
entidades market comparten su nombre; no alcanza con cambiar el orden de un test.

### 2. P2 — Se pierden nombres observados distintos

Ubicación: `src/data_challenge/pipeline.py:429`, `_canonical_aliases`.

Los propios fixtures contienen `CloudSmith Labs` y `Cloudsmith Labs`. El código
deduplica por `casefold()` y conserva solo el primero. La consigna exige preservar
cada nombre observado distinto. La clave de comparación y la colección de nombres
originales son conceptos diferentes.

Dirección de corrección: preservar strings originales distintos y ordenar con un
desempate explícito, por ejemplo `(name.casefold(), name)`.

Limitación del test público original preparado por el evaluador: su comprobación
de orden usa solo `casefold` sobre un set y no define el desempate entre variantes
de mayúsculas. Esa aserción también requiere aclaración si se conservan ambas
variantes. No se modificó durante esta revisión.

### 3. P2 — El parser puede inventar números al limpiar entradas malformadas

Ubicación: `src/data_challenge/normalization.py:123` y `:143`.

Resultados ejecutados:

```text
parse_usd_amount("12,5")  -> 125
parse_usd_amount("$1$2")  -> 12
```

No hay un contrato de formato que justifique esas transformaciones. Si la coma
representa decimales, 12,5 no significa 125; si representa agrupación de miles,
la agrupación es inválida. Borrar caracteres no equivale a validar formato.

Dirección de corrección: definir la gramática aceptada y validar antes de limpiar.
La suite independiente exige rechazar estas entradas conforme al objetivo de
parsing seguro; esta precisión no estaba enumerada literalmente en el README.

### 4. P2 — Un timestamp extremo rompe el aislamiento por registro

Ubicación: `src/data_challenge/normalization.py:174`.

`0001-01-01T00:00:00+01:00` y `9999-12-31T23:59:59-01:00` son parseables, pero su
conversión a UTC cae fuera del rango representable. `astimezone` lanza
`OverflowError` fuera del bloque que captura errores. La prueba pasa por el lector
market real: una sola observación impide terminar de ingerir el archivo.

Es un caso extremo, de menor prioridad práctica que el matching, pero contradice
la garantía de degradar atributos temporales inválidos sin abortar la corrida.
Dirección de corrección: incluir conversión y validación temporal en el límite
de manejo de errores del parser, sin capturar indiscriminadamente todo el job.

## Diseño y documentación: temas para la defensa oral

- `_name_candidates` recorre todas las compañías y renormaliza sus aliases en cada
  consulta. Incluso los nuevos dominios CRM pasan por esa búsqueda. En el peor
  caso, construir N compañías cuesta O(N²), considerando nombres acotados. Un
  índice de nombre normalizado a conjunto de candidatos evita barridos completos;
  debe mantenerse cuidadosamente al agregar aliases o fusionar entidades.
- La escritura de los dos JSONL es secuencial y directa. Si la segunda falla,
  queda publicado un dataset parcial. No era obligatorio implementar publicación
  atómica; sí conviene saber explicarla para la capa productiva.
- `SUBMISSION.md` afirma que los market sin match se rechazan, pero el código crea
  una entidad si no encuentra candidatos. Crear una entidad market-only puede ser
  correcto; la política documentada debe reflejarlo.
- El nombre canónico se elige como el nombre CRM más corto, no el más reciente.
  No viola una regla explícita del README, pero debe ser una decisión consciente
  y documentada. Los IDs finales son hashes de la identidad, no IDs transparentes.
- No descuento puntos por no implementar scheduler, APIs externas, cloud o una
  base de datos: estaban fuera del alcance obligatorio.

## Evaluación del trabajo con IA

La conversación muestra preguntas concretas sobre timestamps sin zona horaria,
hosts de una etiqueta, NFKD, el bucle de sufijos, Pydantic y códigos de salida.
También cuestionaste correctamente que el starter sin dependencias equivaliera
a una prohibición de librerías. Dijiste que ejecutaste los tests antes de avanzar.
Eso demuestra revisión activa, no solamente aceptación de código generado.

El salto a practicar ahora es inventar ejemplos que contradigan la solución.
Los ocho tests de pipeline existentes reutilizan los mismos fixtures; por eso
pueden pasar sin detectar el caso nuevo de ambigüedad. Una suite escrita por el
mismo agente que implementa puede compartir sus suposiciones equivocadas.

## Próximo paso sugerido

Antes de delegar fixes, explicar con palabras propias:

1. Por qué M2 parece único al procesarlo pero es ambiguo dentro del batch.
2. Por qué ordenar registros no resuelve esa ambigüedad.
3. Qué separarías en etapas y qué tests agregarías antes de tocar la lógica.

Después: corregir con tests de regresión, repetir esta suite y recién entonces
continuar con la práctica independiente de ingesta automatizada.

