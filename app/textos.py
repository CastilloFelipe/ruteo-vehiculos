"""Textos largos de la app (español de Chile). Aquí no hay resultados numéricos: todos los
números que muestra la app se calculan desde resultados/*.csv o en vivo."""

AUTOR = (
    "Proyecto de **Felipe Castillo**, estudiante de Ingeniería Civil Industrial (UDD). "
    "Código en [GitHub](https://github.com/CastilloFelipe/ruteo-vehiculos)."
)

QUE_ES = """
Todos los días, una empresa de distribución tiene que decidir **qué camión visita a qué
clientes y en qué orden**. Es el problema de la *última milla* y tiene dos reglas que lo hacen
difícil:

- **Cada camión tiene una capacidad**: no puede llevar más carga de la que cabe.
- **Cada cliente solo recibe dentro de una ventana horaria** (por ejemplo, un supermercado que
  acepta despachos entre 8:00 y 10:00). Si el camión llega antes, espera; si llega después,
  la entrega no sirve.

El objetivo es atender a todos los clientes recorriendo la **menor distancia total**. A esto se
le llama **VRPTW** (*Vehicle Routing Problem with Time Windows*, ruteo de vehículos con
ventanas horarias).
"""

NIVELES = """
En una cadena de suministro hay decisiones de distinto horizonte. Este proyecto es el tercero
de una serie que recorre los tres niveles:

| Nivel | Pregunta | Horizonte | Proyecto |
|---|---|---|---|
| Diseño de red | ¿Dónde ubico centros de distribución y cómo fluye la mercadería? | Años | [supply-chain-agent](https://github.com/CastilloFelipe/supply-chain-agent) |
| Inventario | ¿Cuánto stock mantengo y cuándo repongo, con demanda incierta? | Semanas a meses | [inventario-estocastico](https://github.com/CastilloFelipe/inventario-estocastico) |
| Ruteo | ¿Qué camión visita a qué cliente hoy y en qué orden? | Un día | **este proyecto** |
"""

SOLOMON = """
Para comparar métodos de forma justa se usa el **benchmark de Solomon (1987)**, el conjunto de
prueba clásico del VRPTW: **56 instancias de 100 clientes** cada una, con un depósito, camiones
iguales y récords (mejores soluciones conocidas) publicados por la comunidad durante décadas.

Las instancias se agrupan en familias según **dónde están los clientes**:

- **C** (*clustered*): clientes agrupados en zonas, como barrios comerciales.
- **R** (*random*): clientes repartidos al azar por el mapa.
- **RC**: una mezcla de ambos.

y según **qué tan apretado es el horario**:

- **Tipo 1** (C1, R1, RC1): ventanas estrechas y jornada corta → cada camión atiende pocos
  clientes y se necesitan más camiones.
- **Tipo 2** (C2, R2, RC2): ventanas amplias y jornada larga → pocos camiones con rutas largas.
"""

METODOS = """
| Método | Idea | Calidad | Tiempo |
|---|---|---|---|
| **Inserción** | Construye rutas desde cero: va insertando cada cliente en la posición que menos distancia agrega sin romper ventanas ni capacidad. | Un punto de partida factible; puede quedar lejos de los récords. | Milisegundos |
| **Búsqueda local** | Parte de la inserción y prueba cambios pequeños (mover un cliente, intercambiar dos, invertir un tramo). Acepta solo los que mejoran, hasta que ninguno mejora. | Mejora, pero se queda en un *óptimo local*. | Segundos |
| **ALNS** | *Adaptive Large Neighborhood Search*: destruye una parte de la solución y la repara, una y otra vez, aprendiendo qué operadores funcionan mejor. Usa recocido simulado para escapar de óptimos locales. | Cerca de los récords. | Segundos a minutos |
| **Gurobi (exacto)** | Formula el problema como un modelo de programación entera y lo resuelve con *branch-and-bound*, que entrega además una **cota inferior**. | Óptimo demostrado, pero solo en instancias pequeñas. | Crece explosivamente con el tamaño |
"""

LIMITACIONES = """
- **Objetivo solo distancia.** Se minimiza la distancia total, con la convención DIMACS de
  truncar cada distancia a un decimal (la misma de los récords publicados). La literatura
  clásica de Solomon minimiza primero el número de camiones y después la distancia; con ese
  criterio los récords serían otros. En una operación real también importan el costo fijo por
  camión, las horas extra y la holgura frente a atrasos.
- **Límite de tiempo.** Las heurísticas corren con un tiempo acotado por instancia (ver la vista
  *Benchmark*). Con más tiempo, o con una implementación compilada, ALNS se acercaría más a los
  récords, que en muchos casos se obtuvieron con horas de cómputo.
- **El exacto solo es viable en instancias chicas.** Gurobi se usa con versiones recortadas
  (los primeros clientes de cada instancia), porque el modelo crece con el cuadrado del número
  de clientes y la licencia gratuita limita el tamaño. Un óptimo con pocos clientes no garantiza
  el mismo desempeño de ALNS con 100.
- **Datos determinísticos.** Demanda, tiempos de viaje y servicio se suponen conocidos. En la
  práctica hay tráfico, clientes que no están y pedidos de último minuto.
"""

CONCEPTOS = [
    ("Ventana horaria",
     "Intervalo **[apertura, cierre]** en que un cliente puede ser atendido. Si el camión llega "
     "antes de la apertura, **espera**; si llega después del cierre, la ruta es **infactible**. "
     "El depósito también tiene ventana: es el horario de la jornada, y los camiones deben "
     "volver antes de que cierre."),
    ("Capacidad del vehículo",
     "Cada cliente pide una cantidad (demanda) y cada camión tiene una capacidad máxima. La suma "
     "de las demandas de una ruta no puede superarla. En las familias tipo 2 la capacidad es "
     "grande y lo que limita es el tiempo; en las tipo 1 suelen apretar ambas."),
    ("Tiempo de servicio y espera",
     "El **tiempo de servicio** es lo que demora la entrega en el cliente (descargar, firmar). "
     "La **espera** ocurre cuando el camión llega antes de que abra la ventana: no recorre "
     "distancia, pero consume jornada. En Solomon el tiempo de viaje es igual a la distancia, "
     "así que una ruta corta en kilómetros también puede ser larga en horas por las esperas."),
    ("Heurística constructiva (inserción)",
     "Una **heurística** es un método que encuentra soluciones buenas rápido, sin garantizar el "
     "óptimo. La *constructiva* arma la solución paso a paso: en cada paso elige un cliente "
     "pendiente y lo inserta en la ruta y posición más baratas que respeten ventanas y "
     "capacidad; si no cabe en ninguna, abre un camión nuevo. Es la base de las demás."),
    ("Búsqueda local y sus movimientos",
     "Parte de una solución y explora sus *vecinas*: soluciones que difieren en un cambio "
     "pequeño. Movimientos típicos: **relocate** (mover un cliente a otra posición o ruta), "
     "**swap** (intercambiar dos clientes), **2-opt** (invertir un tramo de una ruta) y "
     "**2-opt\\*** (intercambiar las colas de dos rutas). Si un movimiento baja la distancia y "
     "mantiene la factibilidad, se aplica. Termina cuando ningún movimiento mejora: un "
     "**óptimo local**, que no necesariamente es el global."),
    ("ALNS: destruir y reparar",
     "En vez de cambios pequeños, ALNS hace cambios **grandes**: un operador de *destrucción* "
     "saca varios clientes (al azar, los más caros, o un grupo cercano entre sí) y un operador "
     "de *reparación* los vuelve a insertar (el más barato primero, o el que más se arrepentiría "
     "de esperar). Es *adaptativo* porque lleva la cuenta de qué operadores han producido "
     "mejoras y los elige con más probabilidad."),
    ("Recocido simulado",
     "Criterio para decidir si se acepta una solución **peor** que la actual. Se acepta con "
     "probabilidad exp(−empeoramiento / temperatura). Al principio la temperatura es alta y se "
     "aceptan empeoramientos (exploración); se va enfriando y al final solo se aceptan mejoras "
     "(explotación). Así el algoritmo puede salir de un óptimo local para encontrar uno mejor."),
    ("Gap contra la mejor conocida",
     "Mide qué tan lejos está una solución del récord publicado: "
     "**gap = distancia / mejor conocida − 1**. Un gap de 2 % significa recorrer 2 % más que el "
     "récord. Un gap de 0 % iguala el récord. No dice que la solución sea óptima: el récord "
     "tampoco tiene por qué serlo."),
    ("Cota inferior y gap de optimalidad (Gurobi)",
     "Mientras resuelve, Gurobi mantiene dos números: la mejor solución encontrada (**cota "
     "superior**) y una **cota inferior**, un valor que *ninguna* solución puede mejorar, "
     "obtenido de relajaciones del modelo. El **gap de optimalidad** = (superior − inferior) / "
     "superior. Cuando llega a 0 %, la solución está **demostrada óptima**. Si se acaba el "
     "tiempo antes, el gap dice cuánto, como máximo, se podría mejorar todavía. Es una garantía "
     "que ninguna heurística entrega."),
    ("¿Por qué el VRP es NP-difícil?",
     "El número de formas de ordenar 100 clientes es 100! (un número de 158 dígitos), y además "
     "hay que repartirlos en camiones. El VRP contiene como caso particular al problema del "
     "vendedor viajero (TSP), que es **NP-difícil**: no se conoce un algoritmo que lo resuelva "
     "de forma exacta en tiempo polinomial. En la práctica, los métodos exactos funcionan con "
     "decenas de clientes y para cientos o miles se usan heurísticas como ALNS."),
]

LEER_INICIO = """
Esta portada resume el problema, los datos y los métodos. La sección **Conclusiones** se
calcula en vivo desde los archivos `resultados/benchmark.csv` y `resultados/exacto.csv`: si
cambian los resultados, cambian los números. Al final hay un glosario de conceptos para quien
está aprendiendo.

Las otras vistas, en el menú de la izquierda:

- **Resolver una instancia**: resuelve cualquier instancia de Solomon y anima el recorrido.
- **Caso Santiago**: planifica un día de reparto ilustrativo en Santiago, sobre un mapa real.
- **Benchmark**: las 56 instancias comparadas con los récords publicados.
- **Exacto vs heurística**: ALNS contra el óptimo demostrado por Gurobi.
"""

LEER_RESOLVER = """
1. Elige una instancia de Solomon. Opcionalmente, **recórtala** a sus primeros N clientes para
   que el problema sea más chico.
2. Elige un método y presiona **Resolver**.
3. Arriba aparecen los indicadores: distancia total, número de camiones, gap contra el récord
   (solo para la instancia completa, porque los récords son de 100 clientes) y si la solución
   respeta todas las reglas.
4. **Mapa**: cada color es una ruta (un camión); el cuadrado negro es el depósito. A la derecha,
   la mejor solución conocida para comparar.
5. **Animación**: presiona *Reproducir* (o mueve el control de tiempo). Cada {vehiculo} es una
   camioneta de reparto que sale del depósito en t = 0 y avanza por su ruta con los tiempos reales del
   horario: se detiene en el cliente mientras espera que abra la ventana y mientras lo atiende.
   El tramo ya recorrido se pinta firme y el cliente cambia de gris al color de su ruta cuando
   queda atendido. Los números junto a cada cliente indican el orden de visita, así que la
   dirección se lee incluso sin reproducir.
6. **Convergencia** (solo ALNS): la mejor distancia encontrada a lo largo del tiempo. La línea
   punteada es el récord: mientras más se acerque la curva, mejor.
7. **Horario de una ruta**: para cada parada, la barra azul clara es la ventana horaria del
   cliente, el rombo la llegada, la barra naranja la espera y la verde el servicio. El servicio siempre debe empezar dentro de la
   ventana.
"""

SANTIAGO_QUE_ES = """
Un **centro de distribución en Pudahuel** (zona logística de ENEA) reparte paquetes a
**{n} clientes** de distintas comunas de Santiago. Cada cliente pide entre 1 y 6 bultos y tiene
su **ventana de entrega**: en la mañana (09:00 a 13:00), en la tarde (14:00 a 18:00) o todo el
día. Las camionetas cargan 40 bultos, salen del centro desde las 08:00 y deben volver a más
tardar a las 18:00.

La pregunta del día: **¿cuántas camionetas deben salir y qué ruta sigue cada una para manejar
el menor tiempo total?**

**Es un caso ilustrativo.** Los clientes son sintéticos: se ubican al azar alrededor del centro
de cada comuna. Los tiempos de viaje salen de la distancia en línea recta × 1,35 (el rodeo
típico por calles) a 28 km/h promedio; no usan la red vial real ni el tráfico.
"""

LEER_SANTIAGO = """
1. Elige cuántos clientes hay hoy, el método y la **semilla**. La semilla decide dónde están los
   clientes, sus ventanas y sus pedidos: la misma semilla da siempre el mismo día. Presiona
   **Planificar el día**.
2. Arriba aparecen los indicadores: cuántas camionetas salen, los **minutos de manejo** en
   total (lo que se minimiza), los km aproximados (minutos × 28 / 60) y la hora en que vuelve
   la última camioneta. El número de camionetas es un resultado: no se minimiza directamente.
3. **Mapa**: cada color es una camioneta y el círculo negro es el centro de distribución. Pasa
   el mouse sobre un cliente para ver su comuna, su ventana, cuántos bultos pide y a qué hora
   llega la camioneta. Se puede acercar y mover como cualquier mapa. Las líneas unen las
   paradas en orden; no siguen las calles.
4. **Animación**: presiona *Reproducir* o mueve el control de la hora. Cada {vehiculo} es una
   camioneta. Sale del centro lo más tarde posible sin atrasar su regreso: así espera en el
   centro y no en la puerta del cliente. Se detiene en cada cliente mientras entrega, y si
   llega antes de que abra la ventana, espera ahí. El cliente pasa de gris al color de su
   camioneta cuando recibe su pedido.
5. **Camionetas**: para cada una, las comunas en el orden de visita (×2 = dos entregas
   seguidas en la misma comuna), los bultos que carga, la hora de salida y de regreso, y sus
   minutos de manejo.
"""

LEER_BENCHMARK = """
Cada instancia de Solomon se resolvió con los tres métodos heurísticos. El **gap** compara la
distancia obtenida con el récord publicado (0 % = igual al récord). El gráfico muestra el gap
promedio por familia: barras más bajas son mejores. La tabla de abajo tiene el detalle por
instancia y se puede filtrar.
"""

LEER_EXACTO = """
Las heurísticas no dicen qué tan lejos están del óptimo verdadero. Para medirlo se recortan
instancias a pocos clientes y se resuelven con **Gurobi**, que entrega el óptimo demostrado
(o, si se acaba el tiempo, una cota inferior). La tabla compara ese óptimo con ALNS. Abajo
puedes repetir el experimento en vivo con 8 a 15 clientes (incluye la animación del recorrido).
"""

GAP_OPTIMALIDAD = """
**Dos gaps distintos, que no hay que confundir:**

- **Gap de Gurobi** (de optimalidad): distancia entre la mejor solución de Gurobi y su cota
  inferior. Si es 0 %, el óptimo está *demostrado*: no existe una solución mejor.
- **Gap de ALNS contra el óptimo**: cuánto más recorre ALNS que ese óptimo. Si es 0 %, ALNS
  encontró el óptimo, aunque por sí solo no puede saberlo.
"""

SIN_BENCHMARK = (
    "Todavía no hay resultados del benchmark (`resultados/benchmark.csv`). Se generan con "
    "`python scripts/benchmark.py`. Mientras tanto puedes resolver instancias en vivo en la "
    "vista **Resolver una instancia**."
)

SIN_EXACTO = (
    "Todavía no hay resultados del experimento exacto (`resultados/exacto.csv`). Se generan con "
    "`python scripts/benchmark.py --solo exacto`. Abajo puedes correr la comparación en vivo."
)
