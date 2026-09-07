# Llevar esta práctica a otra PC

Este repositorio contiene la consigna, la implementación, los tests y la
corrección independiente. La conversación de Codex no vive dentro de Git.

## Clonar en otra computadora

El repositorio remoto es privado. La computadora debe estar autenticada en
GitHub como un usuario con acceso.

En Linux:

```bash
git clone https://github.com/FrancoLionti/Data-oriented-practice.git
cd Data-oriented-practice
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q -p no:cacheprovider
```

Git recrea los fuentes y el historial. La virtualenv no se transporta porque
contiene rutas propias de la PC original y se regenera con los comandos
anteriores.

## Sincronizar trabajo

Antes de empezar en cada computadora:

```bash
git pull --rebase
```

Después de hacer cambios:

```bash
git add -A
git commit -m "Describe el cambio"
git push
```

No trabajar simultáneamente en ambas computadoras sobre la misma rama sin
sincronizar primero.
