// tsconfig-simulator-globals.d.ts -- ambient declarations for the standard
// JS globals this project's TypeScript actually calls that PXT's own
// device-only ambient set (pxt_modules/core/pxt-core.d.ts and friends)
// does not declare. See tsconfig.json's own header comment for how this
// file fits into the standalone `tsc --noEmit` check (sprint 017 ticket
// 008) -- this file is dev-tooling-only, never part of the compiled
// extension or the on-device build.
//
// Why these two, and only these two: `pxt_modules/core/pxt-core.d.ts`
// starts with `/// <reference no-default-lib="true"/>`, so this program
// never gets the real `lib.es2020.d.ts`/`lib.dom.d.ts` -- only whatever
// pxt_modules/core's own .ts/.d.ts files declare by hand for the
// restricted micro:bit device runtime. Searching that entire package
// turned up no declaration, anywhere, for:
//
//   - `console` -- yet `pxt_modules/core/control.ts`'s own `assert()`/
//     `fail()` call `console.log()` unconditionally. This only works
//     because those calls execute in the PXT browser simulator (a real
//     JS engine with a real `console`), never on-device.
//   - `Array<T>`'s iterator protocol -- `pxt_modules/core/pxt-helpers.ts`
//     uses plain `for (let value of arr)` over a generic `T[]`, which
//     needs `Array<T>` to implement `[Symbol.iterator]()`. PXT's own
//     `interface Array<T>` (pxt-core.d.ts) declares `push`/`length`/etc.
//     by hand but never the iterator protocol.
//
// Everything else this project's code calls that looked missing at
// first (Math.abs/max/min/clamp/sign/roundWithPrecision, Number.isNaN,
// bare `isNaN`/`parseInt`, Math.PI and friends) turned out to already be
// declared by `pxt_modules/core/math.ts` and `pxt_modules/core/
// pxt-helpers.ts` -- both listed in `pxt_modules/core/pxt.json`'s own
// `files` manifest, just never included in this repo's `tsconfig.json`
// until this ticket. Pulling in the REAL `lib.es2020.d.ts`/`lib.dom.d.ts`
// instead of hand-declaring these two was tried first and reverted: it
// reintroduces a real `Math`/`Number` VALUE declaration that conflicts
// with PXT's own from-scratch `declare namespace Math`/`const NaN` (a
// namespace cannot merge with a `var` the way it merges with a `class`
// or `function`), producing "Duplicate identifier" errors instead of a
// clean merge. Hand-declaring exactly the two real gaps avoids that
// conflict entirely.

declare const console: {
  log(...args: unknown[]): void;
  error(...args: unknown[]): void;
  warn(...args: unknown[]): void;
};

interface SymbolConstructor {
  readonly iterator: symbol;
}
declare const Symbol: SymbolConstructor;

interface IteratorResult<T> {
  done: boolean;
  value: T;
}
interface Iterator<T> {
  next(): IteratorResult<T>;
}
interface Iterable<T> {
  [Symbol.iterator](): Iterator<T>;
}
interface Array<T> extends Iterable<T> {
  [Symbol.iterator](): Iterator<T>;
}

// pins.i2cReadNumber / i2cWriteNumber are TypeScript helpers defined in
// pxt_modules/core/pins.ts (over the i2cReadBuffer/i2cWriteBuffer shims in
// shims.d.ts). pins.ts as a whole does not type-check under this harness's
// deliberately narrow file list (added 2026-09-02, tsc crashed inside its
// diagnostics), so the two helpers test/linefollow.ts uses are declared
// here with pins.ts's own signatures. Device builds never see this file.
declare namespace pins {
    function i2cReadNumber(address: number, format: NumberFormat, repeated?: boolean): number;
    function i2cWriteNumber(address: number, value: number, format: NumberFormat, repeated?: boolean): void;
}
