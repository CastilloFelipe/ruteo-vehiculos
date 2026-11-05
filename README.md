# Ruteo de vehículos con ventanas horarias (VRPTW)

[![tests](https://github.com/CastilloFelipe/ruteo-vehiculos/actions/workflows/tests.yml/badge.svg)](https://github.com/CastilloFelipe/ruteo-vehiculos/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Gurobi](https://img.shields.io/badge/solver-Gurobi-red)
![Licencia MIT](https://img.shields.io/badge/licencia-MIT-green)

Este proyecto responde la pregunta diaria de cualquier operación de reparto: **¿qué camión visita
a qué clientes, y en qué orden?** Cada camión tiene capacidad limitada y cada cliente solo puede
recibir dentro de su ventana horaria. El objetivo es recorrer la menor distancia total.

El proyecto resuelve las **56 instancias de Solomon**, el benchmark clásico del problema, con
tres heurísticas de complejidad creciente. Compara los resultados contra **las mejores
soluciones publicadas**. En versiones de 25 y 50 clientes, **Gurobi prueba el óptimo**, y eso
permite medir cuánto pierde la heurística.

La app de Streamlit resuelve cualquier instancia. Dibuja las rutas y anima una 🚚 que las
recorre, para ver el orden de las visitas y la espera por las ventanas horarias.

## Resultados

ALNS con **10 segundos por instancia** queda a un **1,6% en promedio** de las mejores soluciones
conocidas. Iguala el récord en las 17 instancias agrupadas (C1 y C2). Las tres etapas se
encadenan: la inserción entrega una primera solución, la búsqueda local la pule y ALNS la
mejora.

| Familia | Instancias | Inserción | + Búsqueda local | + ALNS (10 s) | ALNS = récord | Camiones (récord) | Camiones (ALNS) |
|---|---|---|---|---|---|---|---|
| C1 | 9 | 39.3% | 5.4% | **0.0%** | 9 | 10.0 | 10.0 |
| C2 | 8 | 66.8% | 3.8% | **0.0%** | 8 | 3.0 | 3.0 |
| R1 | 12 | 39.5% | 8.2% | **1.0%** | 2 | 13.2 | 13.6 |
| R2 | 11 | 66.6% | 15.3% | **3.0%** | 0 | 5.5 | 5.0 |
| RC1 | 8 | 42.4% | 12.2% | **2.8%** | 0 | 12.5 | 13.5 |
| RC2 | 8 | 81.7% | 16.4% | **3.0%** | 0 | 6.2 | 5.5 |
| **Total** | 56 | 55.2% | 10.3% | **1.6%** | 19 | 8.6 | 8.6 |

*Porcentajes = brecha en distancia contra la mejor solución conocida (promedio por familia).
"ALNS = récord": instancias con brecha ≤ 0,05%.*

**Cómo leer las familias:**
- **C:** clientes agrupados en zonas.
- **R:** clientes repartidos al azar.
- **RC:** mezcla de las dos.
- **Tipo 1:** ventanas angostas y camiones chicos, con muchas rutas cortas.
- **Tipo 2:** ventanas amplias y camiones grandes, con pocas rutas largas y más difíciles de
  optimizar.

### Exacto vs heurística

Gurobi resuelve un MILP de dos índices a optimalidad sobre los primeros 25 y 50 clientes de una
instancia por familia. Con el óptimo conocido, la brecha de ALNS es exacta y no una estimación.

| Instancia | Óptimo (Gurobi) | Tiempo Gurobi | ALNS (5 s) | Brecha ALNS |
|---|---|---|---|---|
| C101-25 / C201-25 / R101-25 / R201-25 / RC101-25 / RC201-25 | todos probados | < 0,5 s | igual al óptimo | **0%** |
| C101-50 | 362.4 | 0.1 s | 362.4 | 0% |
| C201-50 | 360.2 | 0.2 s | 360.2 | 0% |
| R101-50 | 1044.0 | 0.1 s | 1045.7 | 0.16% |
| R201-50 | 791.9 | 0.3 s | 795.1 | 0.40% |
| RC101-50 | 944.0 | 9.6 s | 957.1 | 1.39% |
| RC201-50 | 684.8 | 1.2 s | 684.8 | 0% |

**Conclusión:**
- ALNS encuentra el óptimo en 9 de 12 casos y queda a menos de 1,4% en los otros tres.
- El exacto no escala: la licencia gratuita de Gurobi limita el modelo a 2000 variables, y el
  VRPTW crece con el cuadrado de los clientes. En 100 clientes o en una operación real, la
  heurística es la herramienta práctica, y el exacto sirve para validarla.

Los datos completos están en [`resultados/benchmark.csv`](resultados/benchmark.csv) y
[`resultados/exacto.csv`](resultados/exacto.csv).

## Métodos

| Etapa | Qué hace | Dónde |
|---|---|---|
| **Inserción** | Construye rutas insertando el cliente más barato en la posición factible más barata (estilo Solomon I1). | `heuristicas.insercion` |
| **Búsqueda local** | Aplica movimientos hasta que ninguno mejora: reubicar, intercambiar, 2-opt dentro de la ruta y 2-opt\* entre rutas (intercambio de colas). | `heuristicas.busqueda_local` |
| **ALNS** | Destruye y repara: quita entre 5 y 25% de los clientes y los reinserta (detalle abajo). | `heuristicas.alns` |
| **Exacto** | MILP de dos índices (detalle abajo). | `exacto.resolver_exacto` |

**ALNS** (Ropke y Pisinger, 2006):
- Quita entre 5 y 25% de los clientes con uno de tres operadores: aleatorio, peor costo o Shaw
  (clientes parecidos en distancia, ventana y demanda).
- Los reinserta con greedy o regret-2.
- Elige los operadores con pesos adaptativos y acepta soluciones peores con recocido simulado.

**Exacto:** MILP de dos índices en Gurobi:
- arcos binarios;
- tiempos de servicio con big-M ajustado por arco, que además elimina subtours;
- carga acumulada estilo MTZ;
- se podan antes los arcos imposibles por ventana o capacidad.

**Detalles que importan:**
- **La factibilidad se verifica aparte.** `evaluacion.evaluar` revisa cada solución:
  - cada cliente se visita una vez;
  - ningún camión supera su capacidad;
  - el servicio empieza dentro de la ventana, con espera permitida;
  - el camión vuelve al depósito a tiempo.

  Los tests corren ese evaluador sobre **las 56 mejores soluciones publicadas**, que salen
  factibles y con el mismo costo.
- **Convención de distancias DIMACS:** distancia euclidiana **truncada a un decimal**. Es la
  convención con que se publicaron los récords que se usan aquí. Sin ella, los costos no
  coinciden (C101 daría 828.9 en vez de 827.3).
- **Velocidad:** cada ruta guarda la hora de inicio más temprana y la más tardía en cada visita.
  Así, verificar una inserción cuesta O(1) por cliente en vez de recorrer la ruta entera. ALNS
  hace unas 700 a 800 iteraciones por segundo en Python puro.

## Limitaciones

- **El objetivo es solo la distancia** (convención DIMACS 2021). La convención clásica de
  Solomon minimiza primero el número de camiones. Por eso ALNS a veces usa más camiones que el
  récord (R1, RC1) y a veces menos (R2, RC2).
- **Las heurísticas no limitan la flota:** usan los camiones que hagan falta. En la práctica
  nunca pasan de 23, bajo el máximo de 25 de las instancias. El exacto sí impone ese máximo.
- **El tiempo es fijo, 10 s por instancia.** Con más tiempo la brecha baja, sobre todo en R2 y
  RC2. Los récords publicados vienen de algoritmos especializados (como HGS) corridos por
  minutos u horas.
- **El exacto está acotado por la licencia** `pip` de Gurobi: 2000 variables y 2000
  restricciones. Con una licencia académica cabe más (`LIMITE_VARIABLES = None` en
  `exacto.py`).

## Cómo correrlo

```bash
pip install -r requirements.txt
pytest -q                                     # evaluador, heurísticas, exacto y app
streamlit run app/streamlit_app.py            # la app
python scripts/benchmark.py --segundos 10     # rehace resultados/ (~4 min con 4 procesos)
```

Las instancias ya vienen en `data/solomon/`. Para descargarlas de nuevo:
`python scripts/descargar_solomon.py`.

```
src/ruteo/
  instancia.py     lectura VRPLIB, distancias DIMACS, recortes de n clientes
  evaluacion.py    factibilidad, distancia y horario de cada ruta
  heuristicas.py   inserción, búsqueda local y ALNS
  exacto.py        MILP en Gurobi
app/               Streamlit: inicio, resolver una instancia (con animación), benchmark, exacto
scripts/           descarga de datos y benchmark
resultados/        CSV del benchmark y del exacto
```

## Parte de una serie

Este proyecto completa tres niveles de decisión de una cadena de suministro:

| Nivel | Pregunta | Proyecto |
|---|---|---|
| Estratégico | ¿Dónde abrir centros de distribución y cómo fluye la red? | [supply-chain-agent](https://github.com/CastilloFelipe/supply-chain-agent) |
| Táctico | ¿Cuánto inventario tener y cuándo reponer? | [inventario-estocastico](https://github.com/CastilloFelipe/inventario-estocastico) |
| **Operacional** | **¿Qué camión visita a quién, y en qué orden?** | **ruteo-vehiculos** |

## Datos y licencia

- **Instancias:** Solomon (1987), *Algorithms for the Vehicle Routing and Scheduling Problems
  with Time Window Constraints*.
- **Formato VRPLIB y mejores soluciones conocidas:** [PyVRP/Instances](https://github.com/PyVRP/Instances).
- **Código:** licencia [MIT](LICENSE).
