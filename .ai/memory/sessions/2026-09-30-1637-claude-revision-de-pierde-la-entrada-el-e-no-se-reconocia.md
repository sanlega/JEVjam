# Revisión de 'pierde la entrada': el E no se reconocía

- **Fecha**: 2026-09-30 16:37
- **Agente**: claude
- **Rama**: main @ ce4b413

## Hecho
- Revisada la jam 16:31: sin cortes de audio (un hueco de 10 ms); el problema era armónico: E (1 de cada 4 compases) sin reconocer → progresión sin aprender y tonalidad saltando F/C/Am.
- Causa: croma de energía; la cuerda grave de Mi tapaba al G#. Experimento sobre 3 jams reales + sintéticas (fmin × exponente): magnitud gana (E 5/5, 22/22, sintéticas 100 %).
- Cambio en analysis._chroma + test de regresión (falla con el código viejo).
- Contador de bloques de audio perdidos (input overflow y cola llena) con aviso en el resumen.

## Retro
- Bien: separar "¿se pierde el audio?" (medido en input.wav) de "¿se pierde la armonía?" (acordes por pulso) llevó a la causa en dos pasos.
- Bien: las jams grabadas sirven de banco de pruebas para elegir parámetros sin volver a tocar.
