# Cómo hacer el simulacro

## Antes de empezar

1. Cerrá cualquier solución previa o material de preparación.
2. Elegí de antemano qué IA vas a usar.
3. Abrí un cronómetro de 90 minutos.
4. Leé `README.md` como si acabaran de compartirte la consigna en una entrevista.
5. No busques una solución completa del ejercicio antes de intentar diseñarla.

El repositorio comienza deliberadamente con **un test aprobado y uno fallando**. El fallo indica que el comando `build` todavía no está implementado; no es un problema de instalación.

Podés preguntarle al asistente de IA todo lo que quieras. La evaluación incluye tu capacidad para dirigirlo y validar lo que produce.

## Distribución sugerida

- Minutos 0–15: entender, enumerar supuestos y diseñar.
- Minutos 15–65: implementar el camino principal.
- Minutos 65–80: tests, casos límite y correcciones.
- Minutos 80–90: completar `SUBMISSION.md` y preparar la explicación oral.

Si a los 45 minutos todavía no generaste ningún output, reducí alcance: resolvé correctamente el camino principal antes de agregar API, base de datos o concurrencia.

## Durante el ejercicio

Conservá en `SUBMISSION.md`:

- supuestos importantes;
- decisiones que tomaste;
- qué tareas le delegaste a la IA;
- una sugerencia de la IA que hayas verificado o descartado;
- trabajo pendiente.

No hace falta registrar cada prompt. Sí hace falta poder explicar cómo mantuviste control técnico.

## Al finalizar

Detené el trabajo al cumplirse los 90 minutos, aunque no esté perfecto. Ejecutá:

```powershell
pytest -q

python -m data_challenge build `
  --crm data/crm_companies.csv `
  --market data/market_data.json `
  --interactions data/interactions.csv `
  --output artifacts/companies.jsonl `
  --rejects artifacts/rejects.jsonl
```

Después volvé a la conversación de preparación y avisá: **“Terminé el primer simulacro”**. Se revisará el código, se ejecutarán casos adicionales y habrá preguntas de seguimiento como en una entrevista.
