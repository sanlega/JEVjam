# Tonalidad por acordes y primer push

- **Fecha**: 2026-09-30 15:16
- **Agente**: claude
- **Rama**: main @ be1656d

## Hecho
- Primer commit y push a github.com/sanlega/JEVjam (main), revisando que no se suban secretos ni grabaciones.
- keyfinder.KeyTracker integrado en conductor (sin --key) y en review; 18 tests nuevos (48 en total).
- Validado con la jam real: C mayor desde el compás 1 (antes G mayor por croma).
- Estado del arte de detección de tonalidad documentado en ARCHITECTURE.md.

## Retro
- Bien: aprovechar una capacidad que ya teníamos (acordes por compás) resolvió lo que los perfiles de croma no pueden con poca historia.
- Mejorable: el bonus del primer acorde impedía seguir modulaciones; los sesgos "de arranque" deben caducar.
