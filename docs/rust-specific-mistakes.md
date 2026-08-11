# Rust-Specific Failure Mode Taxonomy

*Sources: [cve.org](https://www.cve.org/), [RustSec advisory-db](https://github.com/rustsec/advisory-db), [ANSSI Secure Rust Guidelines](https://www.ssi.gouv.fr/en/), [The Rustonomicon](https://doc.rust-lang.org/nomicon/), [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/).*

Entries below are failure modes whose root cause is specific to Rust's language, standard-library, or ecosystem semantics (ownership/borrowing, `unsafe`, panics, trait system, macros, Cargo). Pitfalls that are equally applicable to C/C++ (or any language) and merely *happen* to have been observed in Rust crates are collected separately in [General / Cross-Language Pitfalls](#general--cross-language-pitfalls) at the end of this document.

---

## A — Numeric Correctness

### A.1 — Integer Arithmetic Overflow / Underflow

**Root cause:** Rust silently wraps arithmetic in release builds (`overflow-checks = false` by default). Unsafe allocation code that computes a size via wrapped arithmetic then allocates a too-small buffer.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [CVE-2018-1000810](https://www.cve.org/CVERecord?id=CVE-2018-1000810) | `std` | `str::repeat(n)` multiplied byte length × repeat count without overflow check; wrapped result caused buffer overflow |
| [CVE-2026-44983](https://www.cve.org/CVERecord?id=CVE-2026-44983) | `smallbitvec` | Integer overflow in internal capacity calculation produced an undersized heap buffer |
| [CVE-2026-42199](https://www.cve.org/CVERecord?id=CVE-2026-42199) | `grid` | `Grid::expand_rows()` overflow corrupted the relationship between logical dimensions and backing storage |
| [RUSTSEC-2019-0003](https://rustsec.org/advisories/2019-0003.html) | `smallvec` | `insert_many` size arithmetic overflow before unsafe allocation |

**Common sub-pattern:** `len * size_of::<T>()` or `base + offset` wrapping silently, followed immediately by `alloc(wrapped_size)` and an `unsafe` write past the actual end.

**Mitigation:** Use `checked_mul`, `checked_add`, or enable `overflow-checks = true` in `[profile.release]` for safety-critical builds.

**Also in C/C++:** the same size-calculation-then-heap-overflow pattern is a classic C bug (`malloc(n * size)` overflowing before allocation); C leaves signed overflow as undefined behaviour and unsigned overflow as silent wraparound. What is Rust-specific here is the debug/release split and the `checked_*`/`overflow-checks` mitigation vocabulary.

---

### A.2 — Silent Truncation via `as` Casting

**Not the same as arithmetic overflow.** The `as` operator for integer-to-integer casts silently truncates to the target width — no panic in any build profile, and no overflow flag. This is distinct from `+`, `-`, `*` which at least panic in debug mode.

```rust
let x: u32 = 0x1_0000_0042;
let y: u8 = x as u8;   // silently 0x42 — no warning, no panic
```

**Dangerous patterns:**
- Casting a computed length `usize → u32` before using it as a C `size_t` surrogate.
- Casting signed to unsigned: `(-1i32) as u32 == u32::MAX`.
- Casting raw pointer addresses: `ptr as usize` then back — round-trip only safe if alignment preserved.
- Slice length cast: `*const [u16] as *const [u8]` does **not** halve the element count; the slice metadata remains the original length, giving a dangling range.

**Guideline (ANSSI LANG-ARITH):** The `as` cast MUST NOT be used as a substitute for checked conversion when the target type is narrower. Use `u8::try_from(x)?` or `u32::try_from(len)?` instead.

**Platform dimension:** `usize` is 4 bytes on 32-bit targets but 8 bytes on 64-bit. Code that assumes `usize == u64` silently truncates indices when cross-compiled for embedded/32-bit targets.

**Also in C/C++:** directly analogous to C's implicit/explicit narrowing conversions (e.g. assigning `int` to `char`, or `(unsigned char)x`), which truncate identically and just as silently. Rust's `as` is essentially the same footgun with different syntax; the mitigation (`TryFrom`/`try_into`) has no first-class equivalent in C.

---

## B — `unsafe` Code Hazards

### B.1 — Unsound `unsafe` Abstractions / Soundness Holes

**Root cause:** A crate exposes a *safe* public API that internally uses `unsafe` in a way that can produce undefined behaviour when called legally. Often the bug is not in the `unsafe` block itself but in the preconditions the public API silently assumes.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [CVE-2019-12083](https://www.cve.org/CVERecord?id=CVE-2019-12083) | `std` | `Error::type_id` override could be used to violate Rust's safety guarantees; the stabilised method was unsound |
| [CVE-2025-24898](https://www.cve.org/CVERecord?id=CVE-2025-24898) | `rust-openssl` | `ssl::select_next_proto` returned a slice pointing into the `server` argument's buffer but with the lifetime of `client`; the returned reference could outlive `server` |
| [RUSTSEC-2018-0001](https://rustsec.org/advisories/2018-0001.html) | `owning_ref` | Fundamentally unsound design; aliasing `&` and `&mut` via raw pointers possible through the safe API |
| [RUSTSEC-2020-0023](https://rustsec.org/advisories/2020-0023.html) | `rio` | `mem::transmute` used to extend a lifetime, creating a reference that could outlive the data it pointed to |

**Common sub-pattern:** `mem::transmute` for lifetime laundering, `unsafe impl Send/Sync` without verifying actual thread-safety, and returning `&T` derived from a `*const T` whose provenance has ended.

**Mitigation:** Every `unsafe` block must carry a `// SAFETY:` comment. Use Miri CI checks. Treat `#[forbid(unsafe_code)]` as the default and escalate to a documented exception.

---

### B.2 — Panic Safety / Exception Safety in `unsafe`

**Root cause:** If code inside an `unsafe` block calls user-provided closures or clone/drop implementations, a panic unwinds the stack while `unsafe` invariants (e.g., a partially-initialized buffer, a mis-set length field) are still broken.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [RUSTSEC-2018-0003](https://rustsec.org/advisories/2018-0003.html) | `smallvec` | Panic during element `clone` left the vector length pointing past live elements; subsequent drop caused double-free |
| [RUSTSEC-2019-0012](https://rustsec.org/advisories/2019-0012.html) | `arrayvec` | Same pattern: panic during `extend` left array partially initialised |
| Similar | `tinyvec`, various iterator adapters | Variations of the same panic-during-clone/drop-in-unsafe bug |

**Common sub-pattern:** `vec.set_len(new_len)` or similar is called *before* filling the new slots; if filling panics, slots with uninitialized or moved-from data are in scope for `Drop`.

**Mitigation:** Use a "drop-bomb" `struct Guard` that resets the length in its `Drop` impl. Never call user code (clone, drop, closures) between incrementing a length counter and actually writing valid data.

---

### B.3 — `static mut` — Unsynchronised Global Mutable State

Every access to a `static mut` variable is `unsafe` because simultaneous reads and writes from different threads (or even signal handlers on the same thread) constitute a data race, which is undefined behaviour.

```rust
static mut COUNTER: u32 = 0;

fn increment() {
    unsafe { COUNTER += 1; }  // UB in multithreaded context
}
```

**Common mistakes:**
- Treating `static mut` as a "global variable" without realising it is inherently racy.
- Using `static mut` in embedded/interrupt contexts where the interrupt and main-line code share state without disabling interrupts.
- Wrapping `static mut` in a function that takes `&mut` — sound only if the caller guarantees no concurrent access, but that guarantee is invisible to the type system.

**Guideline:** Replace `static mut` with `static ITEM: Mutex<T>` (or `AtomicXxx` for primitives). For `no_std` embedded, use RTIC or a critical-section crate, never bare `static mut` shared across interrupt priorities.

**Also in C/C++:** an unsynchronized global/static variable accessed from multiple threads is exactly the same data race, and C/C++ do not require any special marker to declare one. The Rust-specific point is that Rust forces the `unsafe` keyword onto every access, making the hazard visible at the use site instead of looking like ordinary code.

---

### B.4 — Incorrect Atomic Memory Ordering

Rust exposes C++20 atomic orderings (`Relaxed`, `Acquire`, `Release`, `AcqRel`, `SeqCst`). Choosing a weaker ordering than required is a logical data race that is **not** caught by the compiler or by Miri in many cases, and produces intermittent bugs only on weakly-ordered CPUs (ARM, RISC-V, POWER).

| Ordering | What it guarantees |
|---|---|
| `Relaxed` | Atomicity only; no happens-before with other threads |
| `Acquire` | All reads/writes after this point stay after it |
| `Release` | All reads/writes before this point stay before it |
| `SeqCst` | Global total order across all `SeqCst` operations |

**Common mistakes:**
- Using `Relaxed` on a flag that coordinates other (non-atomic) memory writes — the dependent write can be reobserved out-of-order on ARM.
- Pairing a `Release` store with a `Relaxed` load on the reader side, breaking the Acquire-Release synchronization.
- Using `SeqCst` everywhere "to be safe" — correct but expensive on weakly-ordered hardware; the real mistake is being unable to reason about which weaker ordering suffices.
- Load-Compare-Store loops using `Relaxed` for the failure case of `compare_exchange` when `Acquire` is needed.

**Guideline:** Default to `SeqCst` during development (correct and cheap on x86). Downgrade only after explicit proof of correctness for each operation. Test on weakly-ordered hardware (or with `loom`) before shipping.

**Also in C/C++:** Rust's `Ordering` enum is a direct port of the C++11 `std::memory_order` model (`memory_order_relaxed`/`acquire`/`release`/`acq_rel`/`seq_cst`). Every mistake described above (wrong ordering choice, ARM/RISC-V-only bugs, `SeqCst`-everywhere overuse) applies identically to C11 `<stdatomic.h>` and C++11 `<atomic>` code; only the API names differ.

---

### B.5 — `mem::transmute` Without Layout Guarantee

`repr(Rust)` type layout is **not** specified and may change between compiler versions, target platforms, or even between compilations of the same source (generic instantiations). Transmuting between two `repr(Rust)` types is almost always unsound.

**Specifically forbidden patterns (Rustonomicon):**
- Transmuting `&T` to `&mut T` — always UB; the optimizer is free to assume shared references are immutable.
- Transmuting to a reference with an unbound lifetime — creates a reference that can outlive its data.
- Transmuting `Vec<T>` to `Vec<U>` for different `T`/`U` — field order may differ.
- Transmuting between enum variants or padding-containing structs.

**Safe alternatives:**
- For numeric reinterpretation: use `f32::to_bits()` / `f32::from_bits()`.
- For byte access: use `bytemuck` (which performs compile-time layout checks) or `zerocopy`.
- For pointer casts: use `ptr::cast::<U>()`.

**Guideline:** `mem::transmute` between non-`repr(C)` / non-`repr(transparent)` types is PROHIBITED. Any remaining `transmute` must document the layout guarantee it relies on with a `// SAFETY:` comment referencing the specific `repr` attribute.

---

### B.6 — Uninitialized Memory via `mem::uninitialized` / `MaybeUninit` Misuse

`mem::uninitialized()` was deprecated because it is almost always unsound — for most types, an "uninitialized" bit pattern is not a valid value (e.g. `bool`, references, `enum`). `MaybeUninit<T>` is the replacement, but it is routinely misused by calling `assume_init()` before every field has actually been written.

| Advisory | Crate | Description |
|---|---|---|
| [RUSTSEC-2019-0003](https://rustsec.org/advisories/2019-0003.html) | `smallvec` | `insert_many` allowed reading uninitialized memory when the supplied iterator panicked partway through |
| Common pattern | various | `MaybeUninit::uninit().assume_init()` used directly on non-trivial types instead of initializing field-by-field |

**Guideline:** Ban `mem::uninitialized` and `mem::zeroed` for types that are not validly all-zero. Every `assume_init()` call must be paired with a `// SAFETY:` comment proving every field/byte was written on all preceding paths (including early returns and panics).

---

### B.7 — `RefCell` / `Mutex` Runtime Borrow & Lock-Poisoning Panics

Interior mutability (`RefCell<T>`, `Cell<T>`) and locking (`Mutex<T>`, `RwLock<T>`) move Rust's aliasing rules from compile time to run time. Violating them does not cause memory corruption (the abstraction is sound) but does cause a reachable panic:

```rust
let cell = RefCell::new(5);
let _a = cell.borrow_mut();
let _b = cell.borrow_mut(); // panics: already mutably borrowed
```

- A `RefCell` double-borrow (often introduced by innocuous refactors, e.g. calling a method that itself borrows while an outer borrow is still live) panics at runtime instead of failing to compile.
- A `Mutex`/`RwLock` that panics while the guard is held becomes **poisoned**; every subsequent `.lock()` returns `Err` (or panics, depending on the calling code), turning one bug into a cascading failure across all callers of the lock.

**Guideline:** Prefer narrow, non-overlapping borrow scopes; avoid holding a `RefCell` borrow across a call into code that might re-enter the same cell. For `Mutex`, treat poisoning explicitly (`match guard { Ok(g) => ..., Err(poisoned) => ... }`) rather than `.unwrap()`, and keep critical sections panic-free.

---

### B.8 — Reading Uninitialized Padding Bytes

Compilers insert padding bytes between struct fields to satisfy alignment; those bytes have **no defined value at all**, not even "unspecified" — they are genuinely uninitialized. Reinterpreting a struct as a raw byte slice (`slice::from_raw_parts(&s as *const S as *const u8, size_of::<S>())`), `memcmp`-ing two structs, hashing raw bytes, or serializing "as bytes" for FFI/wire formats reads those padding bytes — which is undefined behaviour even though no field value is actually misused.

```rust
#[repr(C)]
struct S { a: u8, b: u32 } // 3 padding bytes between a and b, uninitialized
```

**Guideline:** Never reinterpret a struct's raw bytes without accounting for padding. Use `bytemuck`'s `Pod`/`Zeroable` derives (which reject types containing padding at compile time) or `zerocopy`, rather than hand-rolled `unsafe` byte casts. If padding is unavoidable, make it explicit with named filler fields and zero them.

---

### B.9 — Misbehaving Safe-Trait Implementations Corrupting `unsafe` Invariants

Several standard-library and third-party data structures use `unsafe` internally (unchecked indexing, raw pointer arithmetic) while trusting that a *safe*, user-supplied trait impl (`Ord`, `PartialOrd`, `Eq`, `Hash`, `Borrow`) behaves consistently for the lifetime of the structure. The trait itself is safe to implement incorrectly — the compiler cannot verify `Ord` is a genuine total order — so a buggy or adversarial impl (e.g., a comparator whose result depends on external mutable state, or on floating-point `NaN`) does not fail to compile; it corrupts the invariant the `unsafe` code relies on, and downstream unchecked indexing can then read or write out of bounds.

**Documented in:** the Rustonomicon explicitly calls out `Ord`/`PartialOrd`/`Eq`/`Hash`/`Borrow` as traits whose safe-looking contract violations can be leveraged to break `unsafe` code that assumes them (e.g. binary-search-then-`get_unchecked` patterns, or sorted-structure internals).

**Guideline:** Any `unsafe` code that indexes or dereferences based on the result of a safe trait method (`Ord::cmp`, `Hash::hash`, etc.) supplied by a generic type parameter must not assume the trait is implemented correctly — re-validate bounds itself, or restrict the unsafe optimization to trait impls the crate controls.

---

### B.10 — Atomic Data Not Placed in a Proper Memory Section (Embedded / Multi-Core)

On some microcontrollers and multi-core SoCs, an `AtomicUsize`/`AtomicU32` is only truly atomic with respect to other bus masters (a second core, a DMA engine) if it resides in a specific memory region — e.g. a non-cached, shared SRAM section backed by the core's exclusive-monitor (`LDREX`/`STREX` on ARM) rather than a cached alias. Placing atomic data in the default `.data`/`.bss` section, which the linker script may map to cached or per-core-private memory, can make the atomic operation correct from one core's point of view while a second core or DMA engine observes torn or stale values — Rust's `Ordering` model says nothing about the underlying physical memory attributes.

**Guideline:** For cross-core or DMA-visible atomics, explicitly place the data with `#[link_section = ".shared_uncached"]` (or the vendor-specific section name), verified against the linker script and MPU/MMU configuration. Confirm with the chip's technical reference manual that the exclusive-monitor/atomic support actually covers that memory region.

---

## C — Memory and Resource Lifetime

### C.1 — `Rc`/`Arc` Reference Cycles → Leak / No Secure Cleanup

Creating a cycle of `Rc<RefCell<T>>` (or `Arc<Mutex<T>>`) prevents the reference count ever reaching zero. The objects are never dropped; `Drop` is never called.

```rust
use std::{cell::Cell, rc::Rc};
struct Node { next: Cell<Option<Rc<Node>>> }
let a = Rc::new(Node { next: Cell::new(None) });
let b = Rc::new(Node { next: Cell::new(None) });
a.next.set(Some(b.clone()));
b.next.set(Some(a.clone()));
// Neither a nor b is ever freed — verified by Valgrind
```

**Two distinct consequences:**
1. **Memory exhaustion DoS** — long-running servers or parsers processing user input can accumulate leaked cycles.
2. **Security data not erased** — a `Drop` implementation that zeroises a cryptographic key or clears a password buffer is never called. ANSSI Rule LANG-DROP-SEC: security-critical cleanup MUST NOT rely solely on `Drop`.

**Guideline (ANSSI MEM-MUT-REC-RC):** Recursive types that use reference-counted pointers MUST NOT be combined with interior mutability. Use `Weak<T>` for back-edges. For security-critical zeroing, use an explicit destructor call pattern that does not depend on `Drop` being reached.

---

### C.2 — Panicking Inside `Drop`

If `Drop::drop` panics while the thread is already unwinding from a previous panic, Rust calls `std::process::abort()`. This means:
- Resources held by the inner drop (file handles, mutexes, network connections) may not be released.
- Security-critical cleanup (key erasure, secure log flush) does not complete.
- In `no_std` / `panic = "abort"` targets the abort is immediate with no cleanup at all.

```rust
impl Drop for Handle {
    fn drop(&mut self) {
        self.flush().unwrap();  // if flush() panics during another unwind → abort
    }
}
```

**Guideline (ANSSI LANG-DROP-NO-PANIC):** `Drop::drop` implementations MUST NOT panic. Use `let _ = self.flush()` or log the error rather than unwrapping; critical cleanup must be infallible or use a separate fallible teardown method called before drop.

**Also in C/C++:** the direct analog is a C++ destructor throwing an exception while another exception is already propagating — `std::terminate()` is called, exactly mirroring Rust's abort-on-double-panic behaviour. C has no destructors, but the equivalent "cleanup handler fails during error unwinding" hazard exists in any `goto cleanup` / `atexit` style error path.

---

### C.3 — `mem::forget` / `ManuallyDrop` Bypassing Secure Cleanup

`mem::forget(x)` is safe Rust and compiles without warning. It discards a value without running its `Drop` implementation. This is intentionally used for FFI hand-offs, but misuse silently skips zeroing, unlocking, or file-closing logic.

**Specific security consequence:** A `Zeroize`-on-drop key type whose `Drop` erases the key material from memory can be bypassed by calling `mem::forget(key)` — the raw bytes remain in memory, potentially recoverable from a heap dump or core file.

**Other leak vectors (all safe Rust):**
- `Box::leak(b)` — intentionally leaks; misuse skips cleanup.
- `Rc`/`Arc` cycles (C.1).
- `std::mem::ManuallyDrop<T>` wrapping without a matching `ManuallyDrop::drop` or `ManuallyDrop::into_inner`.
- `Box::into_raw` / `Rc::into_raw` / `Arc::into_raw` without a matching `from_raw` to reconstruct and drop.

**Guideline (ANSSI MEM-FORGET, MEM-LEAK, MEM-MANUALLYDROP):**
- `mem::forget` MUST NOT be used in security-sensitive code.
- Every `into_raw` call MUST have a corresponding `from_raw` call on all execution paths (including error paths).
- Enable Clippy lint `#![deny(clippy::mem_forget)]` in crate roots for crates that handle sensitive data.

---

### C.4 — Unsound `Pin`/`Unpin` Misuse and Self-Referential Struct Moves

`Pin<P>` exists to guarantee that a value will never move in memory again, which `async` code relies on to hold internal self-references (a generator's local variables pointing into its own state). Implementing `Unpin` for a type that is not actually safe to move, or using `unsafe` to move/replace data behind a `Pin`, silently breaks that guarantee and corrupts the self-referential pointers — usually manifesting as memory corruption only under specific poll/move sequences, making it hard to reproduce.

**Common mistakes:**
- `unsafe impl Unpin for MyFuture {}` added "to make the borrow checker happy" without actually verifying the type has no internal self-references.
- Using `mem::swap`, `mem::replace`, or `ptr::write` on `Pin<&mut T>` via `Pin::get_unchecked_mut()` without upholding the pinning invariant.
- Building a custom `Future`/`Stream` combinator by hand and forgetting that once a value is pinned it must stay at that address until dropped.

**Guideline:** Prefer `pin_project` (or `std::pin::pin!`) instead of hand-written `unsafe` pin projections. Never add `unsafe impl Unpin` without a documented proof that the type contains no self-references.

---

### C.5 — Drop Order Mistakes

Rust has two different, easily confused drop-order rules: struct/tuple **fields drop in declaration order** (top to bottom), while **local variables drop in reverse declaration order** (last declared, first dropped). Code that reorders struct fields "for readability", or relies on a `Drop` impl's side effects happening before/after a sibling field's `Drop` (e.g. a lock guard must release before the data it guards is torn down, or a hardware handle must close before its logger), can silently break that ordering with no compiler warning — Rust does not treat drop order as part of a type's documented contract unless the author says so.

**Guideline:** When field drop order matters, document the dependency directly above the struct definition, or wrap the ordering-sensitive fields in a small struct with an explicit `Drop` impl that sequences them deliberately. Never rely on remembering the field-vs-local rule during review — verify it explicitly.

---

### C.6 — Manual `Drop` + `Copy`-Like `ptr::read` Without `mem::forget` → Double Drop

`ptr::read(src)` performs a bitwise copy out of `src` **without** invalidating `src` — the compiler still considers the original location live and will run its `Drop` impl later (e.g. when the enclosing container is itself dropped or reassigned), running the destructor twice on what is logically "the same" resource: double-free, double-close, or double-unlock.

**Example:** a `Vec`-like or arena-like container reading an element out with `ptr::read` to return it to the caller, but forgetting to also mark the original slot as logically moved-out (via `mem::forget` on the stale handle, `ManuallyDrop`, or shrinking the container's length *before* the value becomes observable). Several historical `smallvec`/`arrayvec` advisories (see B.2) stem from exactly this shape.

**Guideline:** Every `ptr::read` of a `!Copy` value must be paired, on the same control-flow path, with either shrinking the owning container's length/state before the value becomes reachable, or `mem::forget`/`ManuallyDrop` on the source location. Prefer safe alternatives (`Vec::remove`, `Option::take`) over raw `ptr::read` wherever possible.

---

### C.7 — Cross-Thread Use of `Rc`/Reference-Counted Types Without Atomic Backing

`Rc<T>`'s reference count is a plain, non-atomic `Cell<usize>` — cheap, but only sound for single-threaded use; `Rc<T>` is deliberately `!Send`/`!Sync` to prevent it crossing threads. Manually forcing it across threads (`unsafe impl Send` on a wrapper, or defeating the auto-trait via transmute) reintroduces a data race on the reference count itself: two threads incrementing/decrementing concurrently can lose updates, causing the count to reach zero while a live reference still exists (dangling pointer) or never reach zero (leak).

**Example:** [RUSTSEC-2020-0029](https://rustsec.org/advisories/2020-0029.html) (`futures-intrusive`) — a type was falsely marked `Send`, allowing exactly this cross-thread reference-count race.

**Guideline:** Never wrap `Rc<T>` to force `Send`/`Sync`. Use `Arc<T>` (atomic refcount) for any type that might cross a thread boundary, even if "in practice" only one thread touches it at a time — the guarantee must hold structurally, not by convention.

---

## D — FFI Boundary Safety

### D.1 — Panics Unwinding Across Language Boundaries

Prior to Rust 1.81.0, a Rust panic unwinding into C code was **undefined behaviour** (the C stack frames have no unwinding tables). Since 1.81.0 it is defined to terminate, but it still skips C++ destructors and C cleanup code (`pthread_cleanup_push` handlers, etc.).

**Pattern:**

```rust
// Pre-1.81 or with C++ frames on the stack: UB
#[unsafe(no_mangle)]
pub unsafe extern "C" fn process(ptr: *mut Data) {
    let d = &mut *ptr;
    do_work(d); // if this panics, C++ dtors above are skipped
}
```

**Correct pattern:** Wrap the entire function body in `std::panic::catch_unwind` and return an error code:

```rust
#[unsafe(no_mangle)]
pub unsafe extern "C" fn process(ptr: *mut Data) -> i32 {
    std::panic::catch_unwind(|| unsafe { do_work(&mut *ptr) })
        .map(|_| 0)
        .unwrap_or(-1)
}
```

**Guideline (ANSSI FFI-NOPANIC):** Every `extern "C"` function exported from Rust MUST either guarantee it cannot panic (e.g., by using only infallible operations) or use `catch_unwind` to prevent propagation. Pin to Rust ≥ 1.81 for all FFI-heavy projects.

---

### D.2 — Non-Robust Types at the FFI Boundary (enum, bool, References)

Rust's type system gives `bool`, `enum`, and references validity invariants that C does not enforce. Passing an integer from C into a Rust `enum` parameter without a bounds check creates an **invalid discriminant** — which is immediate undefined behaviour even before the value is matched on.

```rust
#[repr(u8)]
enum Color { Red = 0, Green = 1, Blue = 2 }

#[unsafe(no_mangle)]
pub unsafe extern "C" fn paint(c: Color) {  // ← UB if C passes 99
    match c { Color::Red => ..., ... }
}
```

**Similarly:** A `*const T` from C cast directly to `&T` is UB if the pointer is null, dangling, or misaligned — the reference type carries a non-null, aligned, valid invariant.

**Guideline (ANSSI FFI-NOENUM, FFI-CK-NONROBUST):**
- Never accept `enum` values directly at an FFI boundary; instead accept the underlying integer type and convert with a checked function (e.g., using `num_enum` crate).
- Never cast a C pointer directly to a Rust reference; use `ptr.as_ref()` / `ptr.as_mut()` which return `Option<&T>` and perform a null check.
- Never construct a Rust `bool` from a foreign byte without checking it is `0` or `1`.

---

### D.3 — `#[repr(packed)]` Unaligned References

`#[repr(packed)]` removes padding between fields to match a C bit-for-C layout, but this can place a field at an address that does not satisfy its natural alignment. Taking a normal Rust reference (`&field`) to such a field is instant undefined behaviour, because references always carry an alignment invariant — even if the reference is never dereferenced.

```rust
#[repr(packed)]
struct Header { flag: u8, value: u32 }

let h = Header { flag: 1, value: 42 };
let r = &h.value; // UB: `value` may be at a misaligned address
```

**Guideline:** Never take a direct reference to a field of a `#[repr(packed)]` struct. Read/write the field by value (`let v = h.value;` — this copies through `read_unaligned` under the hood) or use `addr_of!`/`addr_of_mut!` to obtain a raw pointer without creating an intermediate reference.

---

### D.4 — `#[unsafe(no_mangle)]`/`export_name`/`link_section` Symbol & Linker Hazards

Since the Rust 2024 edition, attributes that affect linkage/ABI (`no_mangle`, `export_name`, `link_section`) must be written as `#[unsafe(no_mangle)]` etc., because they are inherently unsafe: they can cause silent symbol collisions at link time. Two crates (or a crate and the final binary) exporting the same symbol name via `no_mangle` is **not** a compile error — the linker picks one, and calls to the "other" symbol silently jump to unrelated code (undefined behaviour, not necessarily even a link error, especially with weak symbols or C interop). Similarly, `link_section` can misplace static data into a section with the wrong properties (e.g. a non-writable `.rodata`-like section, wrong alignment, or a section not included in the final image), causing corruption or silent discard by the linker.

**Guideline:** Prefer mangled symbols; when `no_mangle`/`export_name` is required for FFI, use a crate/library-specific prefix to avoid collisions, and verify with `nm`/a linker map that only one definition of the exported symbol exists in the final binary. Treat `link_section` placement as reviewed, linker-script-verified configuration, not decoration.

---

## E — Denial of Service

### E.1 — Reachable Panics and Unbounded Resource Consumption

**Root cause:** Rust's `panic!` terminates a thread (or the process in `no_std`). An attacker-controlled input that triggers a panic is a DoS vector. Separately, missing limits on allocation or recursion allow memory exhaustion.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [CVE-2022-24713](https://www.cve.org/CVERecord?id=CVE-2022-24713) | `regex` | Built-in ReDoS mitigations had a bypass; crafted regexes or inputs caused excessive CPU time |
| [CVE-2026-34219](https://www.cve.org/CVERecord?id=CVE-2026-34219) | `libp2p` Gossipsub | Remotely reachable `panic` in backoff expiry handling; unauthenticated attacker can crash the node |
| [CVE-2026-33040](https://www.cve.org/CVERecord?id=CVE-2026-33040) | `libp2p` Gossipsub | Attacker-controlled PRUNE backoff value used in unchecked time arithmetic, causing wrap and potential panic |
| [CVE-2026-35405](https://www.cve.org/CVERecord?id=CVE-2026-35405) | `libp2p` rendezvous | No limit on namespaces a single peer can register; exhausts server memory |
| [CVE-2026-35457](https://www.cve.org/CVERecord?id=CVE-2026-35457) | `libp2p` rendezvous | Pagination cookies stored without bounds; unauthenticated peer causes unbounded allocation |
| [RUSTSEC-multiple](https://rustsec.org/advisories/) | `serde_yaml`, `bincode`, `serde_json` | Deeply nested input causes unbounded recursion → stack overflow |
| [CVE-2025-62162](https://www.cve.org/CVERecord?id=CVE-2025-62162) | `cel-rust` | Certain malformed CEL expressions caused the parser to panic |

**Common sub-patterns:**
- Missing depth limit in recursive parsers/deserializers.
- Trusting attacker-supplied count/size fields to pre-allocate memory without a cap.
- Arithmetic involving attacker-controlled numbers used with unchecked operators.

**Mitigation:** Validate all size/depth/count fields from untrusted sources before allocating or recursing. Prefer iterative designs for parsers. Use `Vec::try_reserve` rather than `Vec::reserve` for attacker-controlled sizes.

---

### E.2 — `Default` Trait Infinite Recursion

A subtle Rust-specific trap: using `..Default::default()` in a struct initializer to fill remaining fields calls `Default::default()` on the **whole struct**, not on individual fields. This creates infinite recursion.

```rust
struct S { a: u32, b: u32 }
impl Default for S {
    fn default() -> Self {
        S { a: 0, ..Default::default() }  // ← calls S::default() recursively → stack overflow
    }
}
```

The intent is usually to zero-initialize `b`, which requires explicitly writing `b: 0` or deriving `Default`.

**Guideline:** Never use `..Default::default()` inside the `Default` implementation of the same type. Use `#[derive(Default)]` wherever possible; it never produces this pattern.

---

### E.3 — Blocking Synchronous Operations in Async Contexts

Async executors (Tokio, async-std, etc.) run many logical tasks on a small pool of OS threads. Any call that blocks the underlying thread — synchronous file/network I/O, `std::thread::sleep`, holding a `std::sync::Mutex` across an `.await` point, or a CPU-intensive computation — starves every other task scheduled on that thread, producing latency spikes, missed deadlines, or full deadlock if the blocked task is itself waiting on another task queued behind it.

```rust
async fn handler(state: Arc<std::sync::Mutex<State>>) {
    let guard = state.lock().unwrap();
    some_async_call().await; // blocks the executor thread while holding a sync Mutex
}
```

**Mitigation:** Use async-aware locks (`tokio::sync::Mutex`) when a lock must be held across `.await`, or restructure so the lock is dropped before awaiting. Offload blocking/CPU-bound work with `tokio::task::spawn_blocking` / `block_in_place`. Enforce with `clippy::await_holding_lock`.

---

### E.4 — Unbounded Channels / Queues → Memory Exhaustion

`tokio::sync::mpsc::unbounded_channel`, `crossbeam::channel::unbounded`, and similar APIs impose no limit on how many messages can be buffered. If a producer can outpace its consumer (including under attacker control, e.g. one connection per inbound message), the channel's internal queue grows without bound until the process runs out of memory.

**Guideline:** Prefer bounded channels sized to a deliberate backpressure policy; when the queue is full, apply backpressure (block/await) or drop-with-metric rather than growing unboundedly. Reserve unbounded channels for cases where the producer count and rate are provably bounded.

---

### E.5 — `unwrap`/`expect` and Swallowed-Error Anti-Patterns as Panic Sources

`Result`/`Option` make error handling explicit, but two common anti-patterns turn that explicitness back into either a crash or a silent failure:

- `unwrap()` / `expect()` on a `Result`/`Option` derived from external input (parsing, I/O, deserialization) turns any malformed input into a reachable panic — see E.1.
- `let _ = fallible_io_call();` silently discards an `Err`, so failures (e.g. a failed `flush()`, a failed `write()`) go unnoticed and unhandled, which is especially dangerous for security-relevant operations (audit logging, permission changes) that appear to have "succeeded".
- Using `panic!` for conditions that are recoverable in `no_std`/kernel/embedded contexts, where the configured panic handler may `abort()` the whole system rather than unwind.

**Guideline:** Forbid `unwrap`/`expect` outside of tests and cases with a proven invariant (documented with a comment explaining why it cannot fail). Enable `clippy::unwrap_used`, `clippy::expect_used`, and `#[must_use]` on fallible operations; never discard a `Result` with a bare `let _ =` for I/O or security-relevant calls.

---

### E.6 — Async Cancellation Safety (Future Dropped Mid-`.await`)

Unlike a thread, which runs to completion unless explicitly killed, a Rust `Future` can be dropped at any `.await` point — via `select!`, `timeout`, or the parent task simply being cancelled/dropped — and execution just stops there; there is no automatic `finally`-equivalent. Code that assumes "the rest of this async fn will always run" after an `.await` (releasing a lock, decrementing a counter, completing a two-phase state change, sending a completion notification) can leave that state permanently inconsistent if cancelled at exactly that point.

**Example:** `select! { _ = timeout => {}, _ = do_transfer() => {} }` where `do_transfer` debits one account then awaits before crediting the other — a timeout cancels the future between the two steps, leaving the debit applied but not the credit.

**Guideline:** Structure async state machines so every `.await` point represents a valid, resumable-or-abandonable state ("cancellation-safe", per the `tokio::select!` documentation), or move non-cancellation-safe sequences into a detached `tokio::spawn` task (not directly cancelled by the caller dropping its handle) plus explicit cleanup.

---

### E.7 — Forgetting to Poll a Future (Silent No-Op)

A `Future` does nothing at all until it is polled (via `.await`, an executor, or `futures::executor::block_on`) — merely calling an `async fn` performs zero work: no request is sent, no timer starts. Because futures are only `#[must_use]`-warned, not enforced, and are trivially droppable, a future created and then dropped without ever being awaited (e.g. forgotten in `let _ = some_async_fn();`, or an unreached `join!`/`select!` branch) silently does nothing instead of failing loudly.

**Example:** `async fn send_metrics() { .. }` called as `let _ = send_metrics();` inside an async context compiles cleanly and silently never sends anything, because the returned `Future` is dropped unpolled.

**Guideline:** Promote `#[warn(unused_must_use)]` on `Future`-returning calls to `deny`. Never bind an unawaited future to `_` or a throwaway `let` without a comment explaining why it is intentionally not awaited.

---

## F — Filesystem and Platform Safety

Issues previously catalogued under this category (TOCTOU/path-traversal, Windows command-line escaping) are not specific to Rust's language semantics — the same bug classes affect any language performing filesystem or process operations. They are covered in [General / Cross-Language Pitfalls](#general--cross-language-pitfalls) below, retaining Rust-ecosystem examples for context.

---

## G — Application-Level Security

### G.1 — Inconsistent `PartialEq`/`Hash`/`Ord` Implementations Corrupting Hash-Based Collections

Rust requires (but does not enforce at compile time) that manually-written `PartialEq`, `Hash`, and `Ord`/`PartialOrd` implementations agree: if `a == b`, then `hash(a) == hash(b)` must also hold, and the `Ord` total order must be consistent with `PartialEq`. Violating this contract is not memory-unsafe, but it silently corrupts `HashMap`/`HashSet`/`BTreeMap` behaviour: lookups can fail to find a key that is "equal" to one already inserted, entries can appear duplicated, or sort order can become non-transitive.

**Common causes:**
- Hand-written `Hash` that only covers a subset of the fields used by the derived/hand-written `PartialEq`.
- Floating-point fields included in a hand-written `Eq`/`Hash` (NaN breaks reflexivity of `==`, so `Eq`'s reflexivity contract is violated).
- A custom `Ord` that does not agree with the type's `PartialEq` (e.g. case-insensitive `Ord` paired with case-sensitive `PartialEq`).

**Security relevance:** these are logic bugs, not UB, but a broken `Eq`/`Hash` on a key type used for authorization/cache lookups (e.g. treating two distinct principals as "equal" for a permission check) can lead to access-control bypass or cache poisoning.

**Guideline:** Prefer `#[derive(PartialEq, Eq, Hash, PartialOrd, Ord)]` over hand-written impls. If a manual impl is required, it must cover exactly the same set of fields across all four traits, and floating-point fields must be excluded from `Eq`/`Hash`/`Ord` (or wrapped in a total-order newtype).

---

### G.2 — Derive Macro Order Dependence and Helper-Attribute Consumption Conflicts

`#[derive(A, B)]` expands each derive macro independently, but many proc-macro derives look for and consume "helper attributes" attached to the same item (e.g. `#[serde(...)]`). When two derives both want to observe or strip the same helper attribute, or a derive's expansion is order-sensitive relative to attributes registered by another, the **textual order** of the derive list can silently change which macro sees which attributes — sometimes producing an "unknown attribute" error attributed to the wrong macro, and sometimes a macro simply ignoring an attribute it never saw, with no error at all.

**Guideline:** Do not assume `#[derive(A, B)]` is commutative when custom derive macros with helper attributes are involved; consult each macro's documentation for required ordering and pin it with a comment where it matters. Prefer macros that namespace their helper attributes to avoid cross-derive ambiguity.

---

## H — Supply-Chain Security

### H.1 — Dependency Confusion / Typosquatting

Many RustSec advisories (marked `informational = "malicious"`) are for crates that impersonate well-known crates with minor name variations (`rustdecimal` instead of `rust_decimal`, `chrono_anchor` instead of `chrono`, etc.) and contain credential-stealing or backdoor code.

**Examples from advisory-db:** `rustdecimal`, `chrono_anchor`, `vec-const`, and dozens of `tracing-*`, `polymarket-*`, `finch-*` clones.

**Mitigation:** Pin dependency versions in `Cargo.lock`. Use `cargo-deny` to allowlist permitted crates. Audit new transitive dependencies in CI. Enable Dependabot / RenovateBot for automated vulnerability alerts.

---

### H.2 — `build.rs` / Proc-Macro Compile-Time Execution

Cargo build scripts (`build.rs`) and procedural macros run arbitrary Rust code at compile time with full filesystem and network access, under the permissions of the developer or CI user. A dependency's malicious or compromised `build.rs` can:
- Exfiltrate environment variables (tokens, SSH keys, AWS credentials).
- Write backdoors into the generated source tree.
- Execute shell commands on the build machine.

This is distinct from H.1 because it applies even to correctly-named but compromised packages.

**Guidelines:**
- Use `cargo-deny` with an allowlist to require explicit review of any dependency that has a `build.rs` or procedural macro.
- Run builds in isolated environments (containers with no network access, no credential files mounted).
- Use `CARGO_NET_OFFLINE=1` in CI to prevent `build.rs` from making network calls.
- Prefer crates with `#![forbid(proc_macro)]` and no build scripts for security-sensitive supply chains.

---

## Summary Table

| Sub-group | Category | Primary CWEs | Key CVEs / Source |
|---|---|---|---|
| A.1 | Integer arithmetic overflow / underflow | [CWE-190](https://cwe.mitre.org/data/definitions/190.html), [CWE-680](https://cwe.mitre.org/data/definitions/680.html) | [CVE-2018-1000810](https://www.cve.org/CVERecord?id=CVE-2018-1000810), [CVE-2026-44983](https://www.cve.org/CVERecord?id=CVE-2026-44983) |
| A.2 | `as` cast silent truncation | [CWE-681](https://cwe.mitre.org/data/definitions/681.html), [CWE-197](https://cwe.mitre.org/data/definitions/197.html) | Rustonomicon; ANSSI LANG-ARITH |
| B.1 | Unsound `unsafe` abstractions | [CWE-119](https://cwe.mitre.org/data/definitions/119.html), [CWE-416](https://cwe.mitre.org/data/definitions/416.html) | [CVE-2019-12083](https://www.cve.org/CVERecord?id=CVE-2019-12083), [CVE-2025-24898](https://www.cve.org/CVERecord?id=CVE-2025-24898) |
| B.2 | Panic safety in `unsafe` | [CWE-415](https://cwe.mitre.org/data/definitions/415.html) | [RUSTSEC-2018-0003](https://rustsec.org/advisories/2018-0003.html) |
| B.3 | `static mut` data races | [CWE-362](https://cwe.mitre.org/data/definitions/362.html), [CWE-820](https://cwe.mitre.org/data/definitions/820.html) | Rustonomicon; ANSSI UNSAFE-NOUB |
| B.4 | Wrong atomic memory ordering | [CWE-362](https://cwe.mitre.org/data/definitions/362.html), [CWE-366](https://cwe.mitre.org/data/definitions/366.html) | Rustonomicon atomics chapter |
| B.5 | `transmute` without layout guarantee | [CWE-843](https://cwe.mitre.org/data/definitions/843.html) | Rustonomicon transmutes chapter |
| B.6 | Uninitialized memory misuse | [CWE-457](https://cwe.mitre.org/data/definitions/457.html), [CWE-908](https://cwe.mitre.org/data/definitions/908.html) | [RUSTSEC-2019-0003](https://rustsec.org/advisories/2019-0003.html) |
| B.7 | `RefCell`/`Mutex` runtime borrow & lock panics | [CWE-667](https://cwe.mitre.org/data/definitions/667.html), [CWE-674](https://cwe.mitre.org/data/definitions/674.html) | Rust std docs (`RefCell`, `Mutex` poisoning) |
| B.8 | Reading uninitialized padding bytes | [CWE-457](https://cwe.mitre.org/data/definitions/457.html), [CWE-908](https://cwe.mitre.org/data/definitions/908.html) | Rustonomicon; `bytemuck`/`zerocopy` docs |
| B.9 | Misbehaving safe-trait impls corrupting `unsafe` invariants | [CWE-664](https://cwe.mitre.org/data/definitions/664.html), [CWE-125](https://cwe.mitre.org/data/definitions/125.html), [CWE-787](https://cwe.mitre.org/data/definitions/787.html) | Rustonomicon "Working with Unsafe" |
| B.10 | Atomic data not placed in proper memory section (embedded) | [CWE-662](https://cwe.mitre.org/data/definitions/662.html), [CWE-667](https://cwe.mitre.org/data/definitions/667.html) | Vendor TRM / linker-script practice |
| C.1 | `Rc`/`Arc` cycles → leak / no secure cleanup | [CWE-401](https://cwe.mitre.org/data/definitions/401.html), [CWE-312](https://cwe.mitre.org/data/definitions/312.html) | ANSSI MEM-MUT-REC-RC, LANG-DROP-SEC |
| C.2 | Panicking inside `Drop` | [CWE-248](https://cwe.mitre.org/data/definitions/248.html) | ANSSI LANG-DROP-NO-PANIC |
| C.3 | `mem::forget` bypassing secure cleanup | [CWE-312](https://cwe.mitre.org/data/definitions/312.html), [CWE-401](https://cwe.mitre.org/data/definitions/401.html) | ANSSI MEM-FORGET |
| C.4 | Unsound `Pin`/`Unpin` misuse | [CWE-825](https://cwe.mitre.org/data/definitions/825.html), [CWE-664](https://cwe.mitre.org/data/definitions/664.html) | Rustonomicon `Pin` chapter |
| C.5 | Drop order mistakes | [CWE-664](https://cwe.mitre.org/data/definitions/664.html) | Rust Reference (destructors) |
| C.6 | Manual `Drop` + `ptr::read` without `mem::forget` → double drop | [CWE-415](https://cwe.mitre.org/data/definitions/415.html) | Historical `smallvec`/`arrayvec` advisories |
| C.7 | Cross-thread `Rc` use without atomic refcount | [CWE-362](https://cwe.mitre.org/data/definitions/362.html), [CWE-416](https://cwe.mitre.org/data/definitions/416.html) | [RUSTSEC-2020-0029](https://rustsec.org/advisories/2020-0029.html) |
| D.1 | FFI panic unwind | [CWE-119](https://cwe.mitre.org/data/definitions/119.html) | ANSSI FFI-NOPANIC |
| D.2 | Non-robust types at FFI boundary | [CWE-843](https://cwe.mitre.org/data/definitions/843.html) | ANSSI FFI-NOENUM |
| D.3 | `repr(packed)` unaligned references | [CWE-704](https://cwe.mitre.org/data/definitions/704.html), [CWE-843](https://cwe.mitre.org/data/definitions/843.html) | Rustonomicon; std `addr_of!` docs |
| D.4 | `no_mangle`/`export_name`/`link_section` linker hazards | [CWE-665](https://cwe.mitre.org/data/definitions/665.html), [CWE-758](https://cwe.mitre.org/data/definitions/758.html) | Rust 2024 edition `unsafe attributes` |
| E.1 | Reachable panics / resource exhaustion | [CWE-400](https://cwe.mitre.org/data/definitions/400.html), [CWE-674](https://cwe.mitre.org/data/definitions/674.html) | [CVE-2022-24713](https://www.cve.org/CVERecord?id=CVE-2022-24713), [CVE-2026-34219](https://www.cve.org/CVERecord?id=CVE-2026-34219) |
| E.2 | `Default::default()` infinite recursion | [CWE-674](https://cwe.mitre.org/data/definitions/674.html) | Rust compiler behaviour |
| E.3 | Blocking sync operations in async contexts | [CWE-667](https://cwe.mitre.org/data/definitions/667.html), [CWE-400](https://cwe.mitre.org/data/definitions/400.html) | `clippy::await_holding_lock` |
| E.4 | Unbounded channels/queues | [CWE-400](https://cwe.mitre.org/data/definitions/400.html), [CWE-770](https://cwe.mitre.org/data/definitions/770.html) | Tokio/crossbeam documentation |
| E.5 | `unwrap`/`expect`/swallowed-error anti-patterns | [CWE-248](https://cwe.mitre.org/data/definitions/248.html), [CWE-252](https://cwe.mitre.org/data/definitions/252.html), [CWE-390](https://cwe.mitre.org/data/definitions/390.html) | `clippy::unwrap_used` |
| E.6 | Async cancellation safety (future dropped mid-`.await`) | [CWE-662](https://cwe.mitre.org/data/definitions/662.html), [CWE-696](https://cwe.mitre.org/data/definitions/696.html) | Tokio `select!` documentation |
| E.7 | Forgetting to poll a future (silent no-op) | [CWE-252](https://cwe.mitre.org/data/definitions/252.html) | `#[must_use]` on `Future` |
| G.1 | Inconsistent `PartialEq`/`Hash`/`Ord` | [CWE-697](https://cwe.mitre.org/data/definitions/697.html), [CWE-1023](https://cwe.mitre.org/data/definitions/1023.html) | Rust API Guidelines |
| G.2 | Derive macro order dependence / helper-attribute conflicts | [CWE-696](https://cwe.mitre.org/data/definitions/696.html) | Proc-macro derive documentation |
| H.1 | Supply-chain / typosquatting | [CWE-1104](https://cwe.mitre.org/data/definitions/1104.html) | Multiple RUSTSEC malicious advisories |
| H.2 | `build.rs` / proc-macro compile-time execution | [CWE-94](https://cwe.mitre.org/data/definitions/94.html), [CWE-426](https://cwe.mitre.org/data/definitions/426.html) | ANSSI LIBS-VETTING |

---

## General / Cross-Language Pitfalls

The following bug classes are **not specific to Rust** — the same root cause and exploitation pattern applies equally to C, C++, or any other systems language. They are retained here (with Rust-ecosystem examples) because they have been observed in Rust crates and are still worth guarding against, but they should not be treated as evidence of a Rust-specific language weakness.

### Incorrect Buffer Sizing in FFI / C Bindings

**Root cause:** When wrapping a C API, the calling code must mirror C's length conventions exactly. Mistakes include off-by-one assertions, using the wrong length argument (before vs. after padding), or forwarding an unchecked user value directly to a C function that trusts it. This class of bug exists identically in native C/C++ code calling the same APIs — Rust's type system does not check preconditions of foreign functions.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [CVE-2026-44662](https://www.cve.org/CVERecord?id=CVE-2026-44662) | `rust-openssl` | `cipher_update` / `Crypter::update` sized the output buffer incorrectly for AES key-wrap-with-padding ciphers; potential heap write past buffer |
| [CVE-2026-41898](https://www.cve.org/CVERecord?id=CVE-2026-41898) | `rust-openssl` | FFI trampolines for PSK/cookie callbacks forwarded the user closure's returned `usize` directly to OpenSSL without clamping or validation |
| [CVE-2026-41681](https://www.cve.org/CVERecord?id=CVE-2026-41681) | `rust-openssl` | `EVP_DigestFinal()` always writes `EVP_MD_CTX_size()` bytes; `MdCtxRef::digest_final` did not guarantee the output buffer was that large |
| [CVE-2026-41678](https://www.cve.org/CVERecord?id=CVE-2026-41678) | `rust-openssl` | `aes::unwrap_key()` had an incorrect assertion (`out.len() + 8 <= in_.len()` instead of `>=`) allowing misuse |
| [CVE-2026-41676](https://www.cve.org/CVERecord?id=CVE-2026-41676) | `rust-openssl` | `Deriver::derive` passed `buf.len()` as both the in/out length parameter to `EVP_PKEY_derive`, which can truncate the derived key silently |
| [CVE-2026-41677](https://www.cve.org/CVERecord?id=CVE-2026-41677) | `rust-openssl` | `*_from_pem_callback` APIs did not validate the length returned by the user's password callback; a callback returning too large a length caused a buffer overread |

**Mitigation:** All lengths crossing an FFI boundary must be validated (clamped, checked against actual buffer size) before use. Treat every value coming *out* of a C callback as untrusted.

---

### TOCTOU / Path Traversal

**Root cause:** Filesystem operations (check-then-use, symlink resolution during recursive delete/extract) are not atomic in any mainstream OS filesystem API — this is a POSIX/Win32 API characteristic, not a Rust one. Between the check and the use, an attacker (or a concurrent thread/process) can swap out a directory for a symlink.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [CVE-2022-21658](https://www.cve.org/CVERecord?id=CVE-2022-21658) | `std` | `fs::remove_dir_all` followed symlinks during recursive deletion; allowed a concurrent unprivileged process to delete arbitrary files |
| [CVE-2022-36113](https://www.cve.org/CVERecord?id=CVE-2022-36113) | Cargo | Crate tarballs could contain symlinks that, after extraction, caused subsequent writes to land outside the intended directory |
| [CVE-2026-5223](https://www.cve.org/CVERecord?id=CVE-2026-5223) | Cargo | Symlinks inside crate tarballs from third-party registries could override source code of another crate |
| [RUSTSEC-multiple](https://rustsec.org/advisories/) | tar, zip, archive crates | "Zip Slip" variants: archive entries with `../` components extract outside target directory |

**Mitigation:** Use the `cap-std` / `cap-primitives` capability-based filesystem API, which opens a directory once and scopes all subsequent operations to that file descriptor, eliminating TOCTOU windows. Always canonicalize and validate archive entry paths before writing.

---

### Platform-Specific Command Escaping (Windows)

**Root cause:** Windows batch-file (`.bat`/`.cmd`) argument escaping has long-standing quirks in `cmd.exe` itself; any language's process-spawning API that shells out to a batch file inherits the same injection risk if it does not special-case it.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [CVE-2024-24576](https://www.cve.org/CVERecord?id=CVE-2024-24576) | `std` | `std::process::Command` did not properly escape arguments when invoking `.bat` / `.cmd` files on Windows; allowed command injection if any argument was attacker-controlled |
| [CVE-2024-43402](https://www.cve.org/CVERecord?id=CVE-2024-43402) | `std` | The fix for [CVE-2024-24576](https://www.cve.org/CVERecord?id=CVE-2024-24576) was incomplete; further bypass was possible |

**Mitigation:** Never pass untrusted input as arguments to shell scripts or batch files. If unavoidable, validate and escape with a dedicated, well-tested quoting library. Pin to Rust ≥ 1.81.0 where the fix is complete.

---

### Missing Trust-Boundary Validation

Business-logic bugs that do not involve any language-specific mechanism (UB, panics, etc.) but have produced serious CVEs in Rust applications, exactly as they would in any language. No type system prevents incorrect authorization or access-control logic.

| CVE / Advisory | Crate | Description |
|---|---|---|
| [CVE-2026-43911](https://www.cve.org/CVERecord?id=CVE-2026-43911) | Vaultwarden | Refresh tokens not invalidated when `security_stamp` rotates (password/KDF change); stale tokens remain valid |
| [CVE-2026-43912](https://www.cve.org/CVERecord?id=CVE-2026-43912) | Vaultwarden | Cross-organization references allowed; group/collection membership could be manipulated across org boundaries |
| [CVE-2026-43913](https://www.cve.org/CVERecord?id=CVE-2026-43913) | Vaultwarden | Unconfirmed org owner could purge the entire vault; invitation flow did not enforce confirmed status before privileged operations |
| [CVE-2026-43914](https://www.cve.org/CVERecord?id=CVE-2026-43914) | Vaultwarden | Login brute-force protection bypassable when email 2FA is enabled |
| [CVE-2026-42559](https://www.cve.org/CVERecord?id=CVE-2026-42559) | RMCP (MCP SDK) | Streamable HTTP server did not validate `Host` header; SSRF / routing attacks possible |

**Common sub-pattern:** Business-logic validation is missing or only partially enforced at one layer (e.g., the API handler) while the data model allows another path to the same privileged action.

---

## Sources

| Source | What's there |
|---|---|
| **[RustSec Advisory Database](https://github.com/rustsec/advisory-db)** | All published Rust CVEs, categorized |
| **["How Do Programmers Use Unsafe Rust?"](https://dl.acm.org/doi/10.1145/3428232)** (Astrauskas et al., OOPSLA 2020) | Empirical study of unsafe usage |
| **["Is Rust Used Safely by Software Developers?"](https://ieeexplore.ieee.org/document/9091052)** (Evans et al., ICSE 2020) | Statistical survey |
| **["Memory-Safety Challenge Considered Solved? An In-Depth Study with All Rust CVEs"](https://arxiv.org/abs/2103.03222)** (Xu et al., 2021) | Categorizes ~all Rust memory CVEs by root cause |
| **[Rustonomicon](https://doc.rust-lang.org/nomicon/)** | Official documentation of `unsafe` invariants |
| **[Clippy lint list](https://rust-lang.github.io/rust-clippy/master/)** | ~600 lints, many capture real bugs |
| **[Ferrocene Language Specification](https://github.com/rust-lang/fls)** | The qualified Rust spec used for safety-critical work; aligned with ISO 26262 |
| **[Rust Coding Guidelines Working Group](https://github.com/rust-lang/rust-clippy/issues)** | Ongoing official effort toward MISRA-like guidelines |
| **[ANSSI Secure Rust Guidelines](https://www.ssi.gouv.fr/en/)** | Concrete rule statements (`LANG-*`, `MEM-*`, `FFI-*`) referenced throughout this document |
