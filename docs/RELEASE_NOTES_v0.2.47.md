# CANCHERIA v0.2.47

Esta versión corrige el falso `coverage=True` observado en producción con `v0.2.46`.

El compilador sí había encontrado cuatro objetivos, pero vinculó los cuatro a una sola acción de disponibilidad. El verificador anterior comprobaba que cada objetivo tuviera algún índice y que todas las acciones estuvieran referenciadas, pero no comprobaba que objetivos independientes dispusieran de acciones independientes. Por eso aceptó el plan y el executor respondió solamente la disponibilidad.

Ahora la cobertura exige una asignación uno-a-uno verificable entre objetivos independientes y acciones canónicas. Si la IA enumera cuatro objetivos y entrega una sola acción, el plan se rechaza antes de ejecutar. El compilador recibe el diagnóstico estructural y regenera el plan completo, hasta tres intentos. Si no logra una cobertura ejecutable, CANCHERIA bloquea la respuesta parcial.

La validación es general y no depende de palabras como “pelota”, “horarios” o “disponibilidad”. También se amplió el límite operativo de cinco a doce acciones, y el compilador recibe el estado de pagos para conservar correctamente objetivos de reservas, efectivo, pagos parciales, torneos y atención humana.

El identificador visible en el próximo log es `2026-10-14_multiobjective_coverage_v239`.
