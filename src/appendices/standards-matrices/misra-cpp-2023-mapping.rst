Rust Cross Reference with MISRA C++ 2023
==========================================

The following tables provide a cross reference between the MISRA C++ 2023 guidelines and their applicability to
Rust. The first table covers guidelines that are applicable to Rust in general, while the second table covers
additional guidelines that are applicable in the presence of unsafe code. The third table lists guidelines that
are not currently applicable to Rust.

This assessment covers all 179 MISRA C++ 2023 guidelines.


Table 1 – Guidelines applicable to Rust in general (safe Rust, no unsafe code present)
--------------------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: auto

   * - Guideline
     - Related MISRA C 2025 guideline
     - Safety-critical Rust rule
     - Category
     - Comment
   * - Rule 0.0.1
     - Rule 2.1
     -
     -
     - MISRA C mapping
   * - Rule 0.0.2
     - Rule 2.1
     -
     -
     - MISRA C mapping
   * - Rule 0.1.1
     - Rule 2.2, Rule 2.8
     -
     -
     - MISRA C mapping
   * - Rule 0.1.2
     - Rule 17.7
     -
     -
     - While must\_use can assist, it is not active by default for all (non-unit returning) functions
   * - Rule 0.2.1
     - Rule 2.8
     -
     -
     - MISRA C mapping, Same rationale as for 2.8 applies for any items that are local to a crate (or module).
   * - Rule 0.2.2
     - Rule 2.7
     -
     -
     - MISRA C mapping
   * - Rule 0.2.3
     - Rule 2.3
     -
     -
     - MISRA C mapping
   * - Rule 0.2.4
     - Rule 8.7 (tangential)
     -
     -
     - Rationale of 0.2.4 applies the same to functions that are local to a crate (or module)
   * - Dir 0.3.1
     - ``-``
     -
     -
     - Rationale of 0.3.1 is language independent and floats work the same in C++ and Rust
   * - Dir 0.3.2
     - ``-``
     -
     -
     - Rationale mentions "unexpected results" and "undefined behavior" as risks -> both could apply to Rust the same as to C++
   * - Rule 4.1.1
     - ``-``
     -
     -
     - While the C++ standard is obviously not relevant, the general principle applies to analogous Specifications (e.g. FLS). However, in the safe Rust subset all syntactically programs not rejected by the compiler should be in compliance (otherwise its a bug in the compiler) Unsafe Rust, must be free of UB in order to conform.
   * - Rule 4.1.2
     - ``-``
     -
     -
     - The rationale applies about features being superseded by safer or better alternatives, applies to Rust.
   * - Rule 4.1.3
     - Rule 1.3
     -
     -
     - MISRA C mapping (not entirely clear why safe rust is applicable, maybe because of "critical unspecified behavior")
   * - Rule 5.7.1
     - Rule 3.1
     -
     -
     - MISRA C mapping, While Rust does support nesting block comments, it is still, or even especially, likely to accidentally comment out code sections unintentionally.
   * - Dir 5.7.2
     - Dir 4.4
     -
     -
     - MISRA C mapping, ``#if 0`` is C/C++ equivalent to ``#[cfg(false)]`` and should also be considered commented out code. It is idiomatic rust to provide code examples in doc comments. This should not be considered commented out code.
   * - Rule 5.10.1
     -
     -
     -
     - It's encouraged to follow the Rust API Guidelines official naming conventions: https://rust-lang.github.io/api-guidelines/naming.html It is important to mention that, for example, using the wrong notation for ``const`` yields a warning but does not stop the language from compiling; using ``#![deny(...)]`` or ``#![forbid(...)]``  would be the best way to ensure some conventions are being followed.
   * - Rule 5.13.4
     -
     -
     -
     - Rust inference handles these sort of cases explicitly. If the type hasn't been specified (ie. ``42u16``, ``42i32``) and the type cannot be inferred from the context, Rust fallbacks to ``i32``. There are, however, contexts where unsuffixed literals are allowed (ie. ``let num = 0x8000;``). To avoid this, depending on the user's needs, using a lint rule such as ``#![warn(clippy::default_numeric_fallback)]`` can help for these cases.
   * - Rule 6.0.4
     -
     -
     -
     - While ``main`` is a reserved entry point for executable Rust programs, it can still be defined inside of modules or as part of a struct's ``impl`` and the program will compile; when defining it in a module it is possible to use it inside the ``main`` that references the entry point, but only when the full namespace name is used:

       .. code-block:: rust

          mod foo {
              pub fn main() {
                  println!("not another fake main!")
              }
          }

          fn main() {
              self::foo::main();
          }

       If we use the notation of ``use self::foo::main;`` at the beginning, the compiler will let us know there are multiple definitions of ``main``
   * - Rule 6.4.1
     - Rule 5.3
     -
     -
     - MISRA C mapping
   * - Rule 6.7.1
     - ``-``
     -
     -
     - Translates to ``static`` variables in Rust. In safe Rust the risk is developer confusion when mutating a static variable with interior mutability. For unsafe Rust the use of ``static mut`` is likely to result in UB
   * - Rule 6.7.2
     -
     -
     -
     - Same reasoning as for Rule 6.7.1
   * - Rule 7.0.1
     - ``-``
     -
     -
     - The rule is mainly concerned with "integral promotion" and its interaction with conversions from bool, which does not apply to Rust since "integral promotion" does not exist here.

       However, the following other minor points can apply to Rust:

       * Confusion caused using &, \|, ~ operators with bool instead of the usual &&, \|\|, ! operators -> The only difference in Rust being the lazy evaluation of their operands

       * When casting a bool to an integral type, its clearer to explicitly name the numerical values that are assigned for each boolean value.

       Depending on whether either or both of these aspects are considered important enough to be mapped to our rules, the classification of Rule 7.0.1 is either both "yes" or both "no".
   * - Rule 7.0.4
     -
     - :need:`gui_RHvQj8BHlz9b`
     - Advisory
     - While bit-shifting in rust can't cause undefined behaviour, panics could be caused.
   * - Rule 8.0.1
     -
     -
     -
     - Rust and Cpp have similar a number of operators and while some footguns are less of a problem (assignment returns (), < and > return bool, which can't be directly compared to integers) it is still possible to write unclear code using operator precedence. There is a warn by default clippy lint about this: https://rust-lang.github.io/rust-clippy/master/#precedence
   * - Rule 8.2.2
     -
     - :need:`gui_ADHABsmK9FXz`
     - Advisory
     - Point 2 of the rationale about missing intent applies to rust "as" casts. specific functions should be used instead.
   * - Rule 8.2.6
     -
     -
     -
     - Just like in C++ roundtripping pointers through pointers to void (union) is allowed, therefore the rationale fully applies. Casting from integer to pointer requires additional care to not create a pointer without provenance. Casting from integers or pointers to void (union in rust) to pointers is allowed in safe rust.
   * - Rule 8.2.7
     -
     -
     -
     - Rationale mentions tools that track pointers. This applies to rust as for example miri misses UB when exposed provenance is used. Casting pointers to integers and back is allowed in safe rust, so this rule also applies to safe rust.
   * - Rule 8.2.8
     -
     -
     -
     - "uintptr\_t" and "intptr\_t" map to "usize" and "isize" in rust. This is marked as applicable to safe rust, because information loss can be important for safe rust as well.
   * - Rule 8.2.10
     -
     - :need:`gui_ot2Zt3dd6of1`
     - Required
     - The same issues regarding stack usage apply to rust. clippy has a lint against unconditional recursion. In safety critical even conditional recursion should be used carefully
   * - Rule 8.9.1
     -
     -
     -
     - This can also lead to "surprising or unspecified behaviour" in rust. See discussion: https://rust-lang.zulipchat.com/#narrow/channel/136281-t-opsem/topic/.E2.9C.94.20Eq.20and.20Ord.20in.20raw.20pointers
   * - Rule 8.14.1
     -
     -
     -
     - In rust the evaluation of the "&&" operator is also short-circuiting, so evaluation of the right-hand side depends on the value of the left-hand side.
   * - Rule 8.20.1
     -
     -
     -
     - Arithmetic overflow in constant evaluation is a compile error if runtime overflow checking is enabled.(https://play.rust-lang.org/?version=stable&mode=release&edition=2024&gist=15b1f64f02b76e6aff6af79730bae8dc difference between debug and release build). It shouldn't happen even if runtime checks are disabled. In some cases (like ``const A: u8 = 200 + 200``) compilation always errors.
   * - Rule 9.4.1
     -
     -
     -
     - Same rationale as in C++ applies. Clippy has a lint that recommends the opposite (clippy::needless\_else) it would have to be disabled.
   * - Rule 9.4.2
     -
     -
     -
     - This rule includes multiple sub-rules some of which map to rust and some don’t:

       1. Maps to rust. Should maybe be forbidden completely (also for if, for and while). https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=04d632b9ed40d0526f6392eaab391ada

       2. Does not map

       3. Does not map

       4. Does not map

       5. Does not map

       6. Maps to rust (there should maybe be an exception for match statements with zero branches to allow conversion from an uninhabited type)

       7. Does not map to rust, as it is checked by the compiler that match statements are always exhaustive. Placement of the default does map to rust as it even influences which branch is taken (unreachable pattern warning)
   * - Rule 9.5.1
     -
     -
     -
     - While Rust does not have C-style for loops, the idea of using iterators instead of manual loops applies to Rust.
   * - Rule 10.1.1
     -
     -
     -
     - The rationale of only taking mutable references as function parameters if it is actually necessary also applies to rust. It might also make sense to create an exception for trait definitions where const might be enough for a specific implementation (like it is done in the C++ rule for templates and virtual functions).
   * - Rule 10.2.1
     -
     -
     -
     - The rationale of making the size of the enum explicit also applies to rust. There should be an exception for enums where at least one variant holds data (which is very common in rust) as there using the repr(uN) specifier stops the compiler from optimizing the enum layout, which might pessimize performance. https://doc.rust-lang.org/nomicon/other-reprs.html#repru-repri
   * - Rule 10.2.3
     -
     -
     -
     - In safe rust overflow of enum variants can occur when "as" casting to a too small integer: https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=65a7d98e2fd1566f32b05eab83dae8a7 Implicit conversion to integer doesn't occur in rust, so the amplification regarding arithmetic or comparisons don't apply. In unsafe rust transmuting to an enum needs to take the enum layout into account (and should be avoided in most cases).
   * - Rule 11.3.2
     -
     -
     -
     - The rationale fully applies to rust. The impact on understandability of the code isn't reduced by the use of references instead of pointers, so it also maps to safe rust.
   * - Rule 13.3.3
     -
     -
     -
     - In Rust it is possible to use different parameter names for a trait definition and the trait implementation. This maps to overriding a function in C++. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=b9fefe14582277f2a79019bd4a26a279 There is a clippy lint against this: https://rust-lang.github.io/rust-clippy/master/#renamed_function_params
   * - Rule 13.3.4
     -
     -
     -
     - In Rust every comparison between functions pointers is unspecified, not only for virtual member pointers. Therefore this rule needs to be extended to cover function pointer/vtable pointer comparisons in general. See https://github.com/rust-lang/unsafe-code-guidelines/issues/589 and https://github.com/Safety-Critical-Rust-Consortium/safety-critical-rust-coding-guidelines/pull/256
   * - Rule 14.1.1
     -
     -
     -
     - rationale applies fully to rust
   * - Rule 15.0.1
     -
     -
     -
     - The requirements of customized destructor and customized copy constructor apply to rust. Rust defaults the destructor by dropping all fields and can create a default copy constructor using "derive(Clone)". Customization can be done by implementing the Clone or Drop trait manually. Even though this is most often used for memory management which requires unsafe code the problem is in general not specific to unsafe rust and therefore this rule also applies to safe rust. In rust this rule would be something like "if the clone trait is implemented (unless it is derived) the drop trait should also be implemented. If the drop trait is implemented the clone trait should not be derived. It should either be implemented manually or not implemented at all."
   * - Rule 16.6.1
     -
     -
     -
     - The issue that symmetric operators that are implemented for different rhs and lhs types can call different implementation depending on the order of parameters maps to rust: https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=9f3b71b8d78f915f55198e61ae7ad1d0 Issues regarding implicit conversion and member/non-member implementations don't map to rust.
   * - Rule 18.4.1
     -
     -
     -
     - The rationale that for certain purposes only non-panicking functions should be used, applies to rust. This is especially the case for Drop implementations as panics in those can easily lead to double-panics which abort the program and extern "C" functions, which aren't allowed to unwind. In rust it is not possible to mark a function as "noexcept".
   * - Rule 18.5.1
     -
     -
     -
     - Rust does not have "noexcept" functions, but extern "C" functions behave similar to them. If a panic tries to exit such a function the program is aborted. Therefore the rationale applies to these functions.
   * - Rule 18.5.2
     -
     -
     -
     - Rationale applies fully to rust.
   * - Rule 19.0.2
     -
     -
     -
     - Similar rationale applies to rust. The list of exceptions would maybe need to be modified to also include variadic functions as those can only be done using a macro in rust currently.
   * - Rule 19.0.3
     -
     -
     -
     - As this rule is at least partially concerned with readability it applies to rust (in a reduced category). In rust there is no risk of UB. In rust there should be an additional exception for crate/file attributes as they have to be at the top of the file. This rule also applies to the use of the include macro which does textual inclusion, although in a more limited form (braces must match and syntax must be valid before expanding). This macro should maybe have a rule that forbids it.
   * - Rule 19.2.1
     -
     -
     -
     - As rust code should use the module system and not the include macro to import files, the risk of this issue is not severe in rust. It is also not possible to create UB due to conflicting definitions. But it is possible to accidentally override items in outer scopes by redeclaring them in inner scopes, which is made easier when using the include macro as the code is not visible inline.
   * - Rule 19.3.4
     -
     -
     -
     - In declarative macros, non-tt metavariables as arguments (e.g. ``expr``) are inserted as AST nodes and cannot be broken up. -> does not apply Using tt-metavariables it  is possible, since they are simply inserted as tokens -> applies Since proc macros also operate on streams of token trees, it applies the same Example
   * - Rule 21.2.3
     -
     -
     -
     - Same rationale applies.
   * - Rule 21.6.1
     -
     -
     -
     - Rationale applies fully to Rust
   * - Rule 21.6.2
     -
     -
     -
     - In safe rust allocating memory is allowed (by creating a box and calling "into\_raw"), therefore memory leaks could still happen if manual memory management is attempted. In unsafe rust the rule fully applies. This rule also applies to usage of ManuallyDrop, as it disables the automatic memory management of smart pointers.
   * - Rule 21.6.3
     -
     -
     -
     - The amplification of this rule needs to be adapted to rust functions. In unsafe Rust the rationale fully applies. Constructors that manage memory can be written in safe rust, therefore this also applies to safe rust.
   * - Rule 22.3.1
     -
     -
     -
     - Same reasoning applies (except for disabling at build time). Applies to every macro of the assert family (debug\_, \_eq). static\_assert maps to const { assert!(expr) }
   * - Rule 28.3.1
     -
     -
     -
     - Rationale applies mostly. Copying of the predicate is not possible (i don't think a single predicate in the std has a Clone bound) or well behaved (using the Clone impl), but the other issues still remain.
   * - Rule 28.6.1
     -
     -
     -
     - This rule maps to functions that are generic and take a type as an argument that can be converted to a container from a reference to the content of the container. If these functions are called with the owning container they don't copy, but if they are called with the non-owning container they do copy. In the std this applies to the Into and From traits and the collections types including Box. The corresponding rust rule should probably disallow using the Into and From traits for these purposes and require the caller to do the copy themselves, if necessary. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=dd9595f92d8a0538379e71c7b5dbf7fb
   * - Rule 28.6.4
     -
     -
     -
     - std::remove/std::remove\_if <-> Vec::retain / Vec::extract\_if (completely different API, doesn’t apply, retain can’t be used wrong and is the more common case) std::unique <-> slice::partition\_dedup (nightly, more flexible, applies) / Vec::dedup (doesn’t apply) std::vector::empty <-> std::Vec::empty (marked must\_use https://doc.rust-lang.org/src/core/slice/mod.rs.html#135, does apply)

       Since it applies to at least some I marked it as applies to safe rust

Table 2 – Guidelines additionally applicable in the presence of unsafe code
---------------------------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: auto

   * - Guideline
     - Related MISRA C 2025 guideline
     - Safety-critical Rust rule
     - Category
     - Comment
   * - Rule 6.0.3
     - ``-``
     -
     -
     - In Rust, Items are always part of their crates namespace. -> The majority of this rule is covered out of the box Functions and variables that are declared ``#[unsafe(no_mangle)]`` can lead to issues.
   * - Rule 6.2.1
     -
     - The module and crate systems of Rust make this practically impossible; if you were to define two types with the same names in different files, when calling them you'd still need to do something like ``let x = foo1::Struct`` and ``let y = foo2::Struct``, otherwise the compiler wouldn't allow a more "global" call of ``use foo1::Struct; use foo2::Struct`` due to ambiguity. HOWEVER, in the case of unsafe Rust/FFI, `#[unsafe(no_mangle)]` can lead to potential issues.
   * - Rule 6.2.2
     - Rule 8.3 (closely related)
     -
     -
     - MISRA C mapping, FFI: an extern declaration shall have a type compatible with the C declaration. Besides that Rust does not separate declaration and definition of functions
   * - Rule 6.5.1
     -
     -
     -
     - Same rationale as for Rule 6.2.4
   * - Rule 6.5.2
     -
     -
     -
     - Same rationale as for Rule 6.2.4
   * - Rule 6.8.1
     -
     -
     -
     - While in safe Rust the borrow checker guarantees that no reference outlives the object it points to, in unsafe Rust one can create raw pointers and dereference them after the pointee has been dropped

       .. code-block:: rust

          let p: *const i32;
          {
              let x = 42;
              p = &x as *const i32;
          }
          // x is dropped, p is dangling
          unsafe { println!("{}", *p); }  // undefined behaviour

       In cases like this, an user COULD potentially get a program that runs and compiles correctly due to the memory not being overwritten yet; however, using a tool like Miri gives us the following result:

       .. code-block:: text

          error: Undefined Behavior: constructing invalid value of type &i32: encountered a dangling reference (use-after-free)
           --> src/main.rs:9:24
            |
          9 |         println!("{}", *p);
            |                        ^^ Undefined Behavior occurred here
            |
            = help: this indicates a bug in the program: it performed an invalid operation, and caused Undefined Behavior
            = help: see https://doc.rust-lang.org/nightly/reference/behavior-considered-undefined.html for further information

          note: some details are omitted, run with `MIRIFLAGS=-Zmiri-backtrace=full` for a verbose backtrace

          error: aborting due to 1 previous error
   * - Rule 6.8.2
     -
     -
     -
     - In safe Rust, we'd get [E0106] if we tried to do the following:

       .. code-block:: rust

          fn f1() -> &i32 {
              let x = 99;
              &x  // error[E0106]: missing lifetime specifier
          }

       However, in unsafe Rust:

       .. code-block:: rust

          fn f1() -> *const i32 {
              let x = 99;
              &x as *const i32  // dangling pointer after return
          }

          fn main() {
              let p = f1();
              unsafe { println!("{}", *p); }  // UB: "x" is long gone
          }

       If we run this normally, we could potentially have the program compile and run just fine, but when using Miri:

       .. code-block:: rust

          error: Undefined Behavior: constructing invalid value of type &i32: encountered a dangling reference (use-after-free)
           --> src/main.rs:9:24
            |
          9 |         println!("{}", *p);
            |                        ^^ Undefined Behavior occurred here
            |
            = help: this indicates a bug in the program: it performed an invalid operation, and caused Undefined Behavior
            = help: see https://doc.rust-lang.org/nightly/reference/behavior-considered-undefined.html for further information
   * - Rule 6.8.3
     -
     -
     -
     - In safe Rust, Error E0597 is emitted: https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=596fdb2179c4c79b494afb51aaa8b40a In unsafe Rust this is possible using raw pointers. (similar to Rule 6.8.2)
   * - Rule 6.8.4
     -
     -
     -
     - In safe rust returning references to temporary objects is prohibited by the borrow checker: https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=10ef1e93de723525be2c60b2aa964be8 In unsafe rust issues can happen either by returning a raw pointer or by extending the lifetime of a reference incorrectly.
   * - Rule 7.0.2
     - ``-``
     -
     -
     - "Contextual Conversions" to bool do not exist in Rust. The cases listed in the rule all require a value of boolean type in Rust.

       The ``as`` operator cannot convert into bool. Conversions via the ``TryInto``/``TryFrom`` traits correspond with ``explicit operator bool`` and are exempted by the Rule.

       For unsafe Rust, one should also consider ``transmute``\ ing into bool where the safety invariant of bool must be ensured. However, this is simply part of the general unsafe Rust rules and does not need a dedicated rule in the Rust guidelines
   * - Rule 8.1.2
     -
     -
     -
     - Rust doesn't allow explicitly specifying the variables captured by a closure. Issues arising from this are also caught by the borrow checker. (similar caveat to Rule 8.1.1 applies here). Capturing raw pointers is not checked, but using them in the closure requires unsafe code, therefore this does map to unsafe rust.
   * - Rule 8.2.1
     -
     -
     -
     - The exact case doesn't map as rust doesn't have class hierarchies like C++ does, but the general issue can occur in unsafe code with trait objects. Casting trait objects to a concrete type should use the "Any" trait, which checks that the conversion is correct (similar to "dynamic\_cast" in C++).
   * - Rule 8.2.3
     -
     -
     -
     - Creating a mutable reference from a constant reference isn't possible in safe code. On raw pointers removing (or adding) constness is possible in safe code, but this can only cause UB in the presence of unsafe code. This guideline applies to unsafe code as the mutation permissions of a pointer need to be taken into account when writing unsafe code. (discussion on zulip about safe rust status: https://rust-lang.zulipchat.com/#narrow/channel/579369-safety-critical-consortium.2Fcoding-guidelines/topic/MISRA.20C.2B.2B.20Mapping.20Interest/near/599857174)
   * - Rule 8.2.4
     -
     -
     -
     - Casting of pointer types (including function pointers) by itself can't cause UB. creating function pointers in safe code is only possible by taking the address of a function, not by casting from a pointer. In unsafe code care must be taken to only call valid function pointers and to not cast a function pointer to a reference to a struct/enum (which can easily lead to UB).
   * - Rule 8.2.5
     -
     -
     -
     - "reinterpret\_cast" maps to "transmute" in Rust and it is similarly dangerous. In Rust one additional exception might be added in regards to "repr(transparent" types. "transmute" is a unsafe function so safe code isn't affected.
   * - Rule 8.2.11
     -
     -
     -
     - Rust can unsafely call variadic functions. As this is interop the C/C++ rules apply directly.
   * - Rule 8.7.1
     -
     -
     -
     - This applies to the unsafe "add" and similar functions on pointers. Creating invalid pointers using these functions is UB. The "wrapping\_add" family of functions doesn't create UB when an invalid pointer is created and are callable from safe code. This rule doesn't apply to safe code as the dereferencing of such pointers is supposed to be covered by rule 4.1.3 and UB can only happen when using the unsafe functions.
   * - Rule 8.7.2
     -
     -
     -
     - The "-" operator isn't available on pointers in rust. This maps to the "offset\_from" family of methods on raw pointers. These are unsafe and introduce UB if used on pointers to different allocations.  Casting pointers to integers and doing arithmetic on them will produce unspecified results if the pointers belong to different allocations and is possible in safe code, but this rule is explicitly concerned with UB and therefore does not apply to safe code.
   * - Rule 8.18.1
     -
     -
     -
     - Union access is not possible in safe rust. Similar it is not possible in safe rust to create a mut reference to a memory location while also holding another reference to it, which would be required to read and write from the same memory location at once. memmove and memcopy map to unsafe rust functions, this part of the rule does apply to unsafe rust. The union part of this rule doesn't apply to rust. The right side of the assignment statement is a "value" expression, not a "place" expression (rust reference). Miri does not report UB in this code: https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=6bafaaf6ac8f638c0f67b3a4d9ad5f4b
   * - Rule 10.1.2
     -
     -
     -
     - The issue of using volatile memory operations correctly maps to rust, as rust has volatile operations. This does not map to safe rust as using volatile operations requires unsafe code. Incorrectly deciding to use non-volatile operations, where volatile operations would be necessary is a problem, but it does not apply to safe rust as accessing MMIO requires unsafe somewhere.
   * - Rule 10.4.1
     -
     -
     -
     - The rationale that inline assembly (or naked functions) should be avoided in favor of language intrinsics applies to rust. In safe rust the use of inline assembly is not possible, therefore this rule doesn't apply to safe rust.
   * - Rule 11.6.1
     -
     -
     -
     - In safe rust the compiler enforces that a variable is initialized when used. While declarations without initialization are possible the compiler checks that it is initialized before it can be used. Since the value cannot be read it is not a "state" that increases complexity. It can even reduce complexity as it may allow removing a "mut" annotation from a variable. In unsafe rust MaybeUninit can be used to delay initialization of variables without the compiler checking correct usage. Here the rule fully applies.
   * - Rule 11.6.2
     -
     - Catching the use of unset variables for operations is done by the Rust compiler after performing definite assignment analysis. The following snippet will give us an error:

       .. code-block:: rust

          fn f() {
              let x: i32;
              let y: i32 = x + 1;
          }

       Diagnostics: used binding ``x`` isn't initialized ``x`` used here but it isn't initialized [E0381]

       In unsafe Rust, there is a chance we read a value from uninit memory and it behaves as UB, not necessarily leading to a program crash/panic
   * - Rule 12.3.1
     -
     -
     -
     - It is not possible to create UB with unions in safe rust, because reading from them is not allowed. Issues with memory leaks because of ManuallyDrop are covered by rule 21.6.2. In unsafe rust the rationale fully applies. In this case this rule applies if there is unsafe code in any place where the union type is accessible.
   * - Rule 15.1.4
     -
     -
     -
     - In safe rust the compiler checks that every member of a object is initialized when the object is created. In unsafe rust (especially using MaybeUninit) this rule applies.
   * - Dir 15.8.1
     -
     -
     -
     - Rust does not allow customizing the behaviour of move or assignment. In unsafe rust move constructors can be simulated using Pin. If and how self-assignment should be taken into account depends on the move API used. For example if both the current and the future location are passed via mutable references self-assignment becomes impossible due to the uniqueness guarantee of mutable references in rust. If raw pointers are used, there is no such guarantee.
   * - Rule 18.1.1
     -
     -
     -
     - In Rust custom panic payloads can be thrown with the function "std::panic::panic\_any". Using this with raw pointers leads to unclear ownership semantics, just like in C++ which should be avoided. Smartpointers or 'static references are exceptions as the ownership semantics are clear. Using custom panic types requires coordination between the panic handler and the panic locations. With only safe code in the panic handler misuse of raw pointer is not possible, therefore it does not map to rust.
   * - Rule 21.6.5
     -
     -
     -
     - Manual destruction/deallocation is not possible in safe rust. In unsafe rust this rule fully applies.
   * - Rule 21.10.1
     -
     -
     -
     - Rust supports C-Variadic function in the same way C does. Using the arguments is only possible in unsafe, therefore it only applies to unsafe rust.
   * - Rule 21.10.2
     -
     -
     -
     - While rust doesn't have these functions they can be used from unsafe rust by using FFI or inline assembly. Using them is often UB, see this thread for discussion and examples: https://github.com/rust-lang/rfcs/issues/2625
   * - Rule 21.10.3
     -
     -
     -
     - Rust std provides no support for interacting with process signals, libraries out of scope for this mapping. Unsafe rust can use platform APIs for this.
   * - Rule 22.4.1
     -
     -
     -
     - Rust std does not provide APIs to edit errno. It can be read using "std::io::Error::last\_os\_error". Unsafe rust can use platform APIs to set errno and therefore this rule applies.
   * - Rule 23.11.1
     -
     -
     -
     - This maps to the standard library functions "from\_raw" on smart pointers and containers in rust. These functions are unsafe, therefore the rule is not applicable to safe Rust
   * - Rule 24.5.2
     -
     -
     -
     - "memmove" and "memcpy" map to "std::ptr::copy" and "std::ptr::copy\_nonoverlapping" in rust. Both are unsafe. Non-trivially copyable types match to rust types that are !Unpin. "memcmp" is not provided by the rust std, but can be implemented by casting to a u8 slice. This has additional risk of UB if there is uninit memory in the buffer, which isn't mentioned in the Rule (only "unspecified" behaviour).
   * - Rule 25.5.1
     -
     -
     -
     - The rust std doesn't provide any locale support. FFI is required to interact with the OS or C APIs therefore maps to unsafe.
   * - Rule 25.5.2
     -
     -
     -
     - Rust std has no locale support. If this is required unsafe has to be used and this rule applies. std::env::var (getenv) returns a string, which is owned and can therefore be modified. errno can be checked from safe rust using std::io::Error::last\_os\_error. The std::io::Error struct implements display and can therefore be turned into a string. The rule doesn't apply to this. If the exact OS error string is required FFI and unsafe rust has to be used and this rule applies.
   * - Rule 25.5.3
     -
     -
     -
     - Only getenv (std::env::var) is accessible from rust. It returns an owned string, therefore this part of the rule does not apply. For the other functions no equivalents are provided in the rust std. As they access system information (time zone, locale, errno) FFI and unsafe are required for use and the rules map to unsafe rust.
   * - Rule 28.6.3
     -
     -
     -
     - Rust uses destructive moves, which don't allow access to moved from objects in safe code. Unsafe code could circumvent this by keeping a pointer to the location.

Table 3 – Guidelines not currently applicable to Rust
-----------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: auto

   * - Guideline
     - Related MISRA C 2025 guideline
     - Comment
   * - Rule 4.6.1
     - ``-``
     - The evaluation order of expressions in Rust is well defined
   * - Rule 5.0.1
     - ``-``
     - Rust does not have trigraph sequences or similar token alternatives
   * - Rule 5.7.3
     - Rule 3.2
     - MISRA C mapping
   * - Rule 5.13.1
     -
     - The compiler itself already prevents this even in ``unsafe`` blocks; the only way to "bypass" this is by using, of course, raw strings (``r"<TEXT>"``).
   * - Rule 5.13.2
     -
     - For Unicode, Rust uses the notation of ``\u{...}`` with a maximum of 6 characters allowed inside of the braces; in the case of the hex ``\x``, it will always take the two hex digits that follow it, yielding a compiling result for something like ``\x41g``. Octal escapes are not supported and ``\0`` is always null; their use could be prevented in production by enabling a lint like ``#![deny(clippy:octal_escapes)]``
   * - Rule 5.13.3
     -
     - Rust manages octal prefixes differently (``0o``), making it unambiguous for the user
   * - Rule 5.13.5
     -
     - The "L" and "l" suffixes do not exist in Rust
   * - Rule 5.13.6
     -
     - Same rationale as for Rule 5.13.5; ``long long`` and the aforementioned suffixes do not exist in Rust. Additionally, the C++ style concatenating does not exist in Rust either; we do have ``concat!()`` but it relies only on whatever expression is used as the argument (calls ``core::stringify`` when needed which yields a ``&'static str``
   * - Rule 5.13.7
     -
     - Rust string literals are always UTF-8, no way to encode them with prefixes such as ``u8`` or ``u``
   * - Rule 6.0.1
     - ``-``
     - In Rust, function, variable and const declarations are clearly visually distinguishable.
   * - Rule 6.0.2
     - Rule 8.11
     - MISRA C mapping
   * - Rule 6.2.3
     -
     - Rust's module system makes duplicate definitions structurally impossible; the compiler would give you the according errors as well ([E0252])
   * - Rule 6.2.4
     -
     -
     -
     - Rust does not have neither a header file mechanism or C++-esque external linkage; Using no_mangle is covered by the more general Rule 6.2.1
   * - Rule 6.4.2
     - ``-``
     - **Applicability:** Not currently applicable to safe or unsafe Rust; applicable to both upon stabilization.

       While Rust does not support C++-style classes, its trait system does support a more limited kind of inheritance. Here, it is possible to have a subtrait relationship where both traits define a function of the same name. However, when a function name is ambiguous Rust will report an error and require disambiguation.

       With the stabilization of https://github.com/rust-lang/rust/pull/148605 it is possible to shadow function in a trait hierarchy as described by this rule
   * - Rule 6.4.3
     - ``-``
     - This rule is highly specific to the C++ class and template system and does not translate to Rust
   * - Rule 6.9.1
     -
     - In rust functions can not be redeclared in general. In traits and their implementation the declaration is written two times, but the types of arguments or the return type cannot be changed. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=ffda211af1767cb708e5bf2c7acd48f1
   * - Rule 6.9.2
     -
     - In Rust the size of the integer and floating point types is defined. The rule doesn't apply to the C++ types intptr\_t and uintptr\_t, so it shouldn't apply to usize and isize in Rust.
   * - Rule 7.0.3
     -
     - In Rust the "char" type isn't comparable or assignable to an integer or bool type. It can only be explicitly converted to and from "u32" which matches the recommendation of using explicit conversion functions.
   * - Rule 7.0.5
     -
     - Rust doesn't have integer promotion or implicit conversion. "as" casting isn't affected by this Rule as it is an explicit cast.
   * - Rule 7.0.6
     -
     - Rust doesn't have implicit integral promotion or overload sets, so the rationale doesn't apply.
   * - Rule 7.11.1
     -
     - Rust doesn't have overloaded functions, so the issues regarding overload selection don't apply. Rust also doesn't have a "NULL" macro. "0" also is not a pointer type in rust and requires explicit syntax to be cast to a pointer.
   * - Rule 7.11.2
     -
     - In Rust arrays don't decay to pointers.
   * - Rule 7.11.3
     -
     - Rust doesn't automatically convert a function pointer to a regular pointer, explicit "as" casts have to be used. The use of such a cast complies with the requirement that the taking of the address should be explicit. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=ca80b6738d968336e473ec38cc9405aa
   * - Rule 8.1.1
     -
     - The borrow checker catches attempts to capture shortlived references in closures. Rust also doesn't have implicit ``this``, so in the closure ``self`` has to be used, which makes it obvious which object is being captured. Closure capture behaves the same in an unsafe block, so this isn't affected by unsafe code. (this mapping depends on a rule about using unsafe to extend the lifetime of references, if such a rule does not exist this would apply to unsafe rust)
   * - Rule 8.2.9
     -
     - Rust has type\_id and type\_name functions that are always evaluated at compile time, even if they maybe take an argument (std::any::{type\_name, type\_name\_of\_val, TypeId::of}). Because they are never evaluated at runtime this rule does not apply. Rust also has a type\_id function that is evaluated at runtime (std::any::Any::type\_id). Because it just takes a self reference and is always evaluated at runtime there is no confusion about potential sideeffects happening at runtime. This function also does not panic.
   * - Rule 8.3.1
     -
     - Rust doesn't allow applying the "-" operator to unsigned number types. Error code E0600 is emitted: https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=df15120669953ba24471999fafc25c8c
   * - Rule 8.3.2
     -
     - Rust doesn't have a unary "+" operator. https://doc.rust-lang.org/reference/expressions/operator-expr.html
   * - Rule 8.18.2
     -
     - In Rust assignment always returns the unit type, so it is not possible to use the return type.
   * - Rule 8.19.1
     -
     - The comma operator maps to the rust code: "{a; b}", which discards the result of expression a and evaluates to the result of expression b. This syntax is not confusing like the comma operator is in C++.
   * - Rule 9.2.1
     -
     - variable declarations in rust use the "let" keyword, so confusion is not possible.
   * - Rule 9.3.1
     -
     - loop and selection statements in rust always require braces, confusion due to indentation is not possible.
   * - Rule 9.5.2
     -
     - The mentioned lifetime issues are resolved by the borrow checker. Using multiple iterator combinators in a for loop is considered idiomatic in Rust.
   * - Rule 9.6.1
     -
     - Rust doesn't have a ``goto`` statement
   * - Rule 9.6.2
     -
     - Rust doesn't have a ``goto`` statement.
   * - Rule 9.6.3
     -
     - Rust doesn't have a ``goto`` statement
   * - Rule 9.6.4
     -
     - In Rust the equivalent of a ``noreturn`` function is a function returning the never type ``!``. That the return type of a function is correct is checked by the type system. There are no special considerations for the never type.
   * - Rule 9.6.5
     -
     - Similar to Rule 9.6.4 the type systems checks that the return type of functions is correct
   * - Rule 10.0.1
     -
     - Declarations in rust can't introcude more than one variable. Destructuring or pattern matching (structured bindings in C++) are explicitly allowed, so should be allowed in Rust as well.
   * - Rule 10.2.2
     -
     - In Rust enums don't implicitly coerce to integers. Overlap of enum and constant names can happen in rust if the enum variant is imported, but an explicit typecast is required. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=ab590204a83054e6a47d6f479f471b13 This rule could be mapped to "don't import enum variants" or "don't shadow other imports", but this feels like it should be a distinct rule as the main issue of implicit coercion doesn't exist in rust.
   * - Rule 10.3.1
     -
     - specific to C++ header files, which don't exist in rust.
   * - Rule 11.3.1
     -
     - In Rust the array type behaves like the C++ type "std::array" in that it has value semantics and the size stays known. As "std::array" is recommended as a compliant alternative, the Rust array type is compliant and this rule doesn't map.
   * - Rule 11.6.3
     -
     - Rust doesn't allow assigning two enum variants the same value, even when done explicitly. Error E0081 is emitted. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=6c72cfac7ae776bf605e7d7f1135a5e6
   * - Rule 12.2.1
     -
     - The rust language doesn't support bitfields. If these guidelines start covering libraries one would have to look at the behaviour of the specific library.
   * - Rule 12.2.2
     -
     - See Rule 12.2.1
   * - Rule 12.2.3
     -
     - See Rule 12.2.1
   * - Rule 13.1.1
     -
     - The standard way of implementing class hierarchies in Rust (storing parent Classes in the Child classes) is always non-virtual, therefore there are no issues about initialization. A diamond can be created using traits, but functions with the same name on parent and child traits need to be disambiguated, therefore there are no issues about call resolution. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=d44a300af1adda1b0b36be11b6bf071b
   * - Rule 13.1.2
     -
     - Rust does not have virtual hierarchies. There also is not a feature that deduplicates struct fields.
   * - Rule 13.3.1
     -
     - Function overriding can be done in Rust with trait default functions. Default functions can always be overridden, no keyword necessary. Overriding also requires no keyword. As this rule is about using the keywords correctly and not doing overrides correctly this does not map to rust. In trait hierarchies ambiguous functions have to be disambiguated at call sites, therefore it is not really function overriding. (https://github.com/rust-lang/rust/pull/148605 would change that, the exact semantics need to be looked at after stabilisation)
   * - Rule 13.3.2
     -
     - Rust does not allow default arguments.
   * - Rule 15.0.2
     -
     - Rust doesn't have move constructors. The signature of the Clone trait (copy constructor) is defined by the trait and deviations from it are a compile error.
   * - Rule 15.1.1
     -
     - Rust does not store V-Tables inline, but always behind a pointer. Creating dyn pointers is done in one operation, an "unsized coercion". It is therefore not possible to observe half constructed V-Tables or RTTI.
   * - Rule 15.1.2
     -
     - This rule is specific to C++ class hierarchies and does not apply to rust, as Rust doesn't have inheritance. The way this usecase is often done in rust (storing the "superclass" as a struct member) guarantees initialization of that object in the same way that struct initialization regularly works (See rule 15.1.4).
   * - Rule 15.1.3
     -
     - Rust does not implicitly convert between types in this way.
   * - Rule 15.1.5
     -
     - Rust has neither initializer lists nor overloaded functions.
   * - Rule 16.5.1
     -
     - In rust only the binary OR and AND operators can be customized, not the logical ones.
   * - Rule 16.5.2
     -
     - Rust does not have a customizable addressof operator.
   * - Rule 17.8.1
     -
     - Rust does not support specialization or overloaded functions.
   * - Rule 18.1.2
     -
     - Rust does not have a language construct for handling panics, nor does it have a throw statement that interacts with it. rethrowing is done with the "std::panic::resume\_unwind" function.
   * - Rule 18.3.1
     -
     - Rust requires a global panic handler to be present. This is called when a panic occurs and controls the behaviour, for example starts unwinding or stops the program in some other way. In rust catching a unwinding program is uncommon. Therefore no unwind catcher is required.
   * - Rule 18.3.2
     -
     - When panics are caught in rust they are returned as the Any trait (see catch\_unwind, JoinHandle::join, PanicHookInfo::payload). This is then downcasted into the expected payload type using the Any trait. For a downcast to work the types need to match exactly. Even otherwise implicit coercions (for example from concrete type to trait object) aren't performed during the downcast. https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=7cfacafd069f8ca6da20e3a265b21f0b Therefore the issue of catching a base class (trait object) doesn't apply to rust, as downcasting to a base class isn't successful if it wasn't already thrown as that base class. This does mean that downcasting to a trait object (for example dyn Debug) is unlikely to be successful as the std panics with payloads of type String on recent editions (https://doc.rust-lang.org/std/macro.panic.html#editions). This issue does not map to this rule, as this rule is concerned with information loss, which does not occur (failing downcasts always need to be handled). The issue of data races is solved in Rust by requiring the panic payload to implement the Send trait (https://doc.rust-lang.org/std/panic/fn.panic_any.html).
   * - Rule 18.3.3
     -
     - In rust there are no function level try-catch blocks. As in normal C++ try-catch blocks care must be taken to avoid accessing objects that are left in an invalid state due to the panic, but this is a more general rule and is covered by rule 18.4.1.
   * - Rule 19.0.1
     -
     - The cfg attribute always applies to the next item. This rule does not applies for it, as its syntax doesn't interleave with the code it applies to. cfg\_select does interleave with the code, but since it requires braces in all but the simplest cases, the rule also doesn't apply here.
   * - Rule 19.0.4
     -
     - It is not possible in rust to remove the definition of a macro after it was introduced.
   * - Rule 19.1.1
     -
     - Rust has no way of checking if a macro definition is available (ignoring proc-macro crimes to run another compiler, but those still don't have issues with being defined in another macro).
   * - Rule 19.1.2
     -
     - Rust requires braces to be matched and therefore the combination between the cfg\_select (similar to preprocessor if) and include macros can't lead to these issues.
   * - Rule 19.1.3
     -
     - Rust does not implicitly set undefined identifiers to the value 0.
   * - Rule 19.2.2
     -
     - Not an issue in rust. If the path give to the include macro (or to a module path attribute) is invalid a compile error is raised and no UB occurs.
   * - Rule 19.2.3
     -
     - Rust supports full raw string literals both in the include macro and in the path attribute of module imports https://play.rust-lang.org/?version=stable&mode=debug&edition=2024&gist=d3b6c099b4eec8733a600204a3db185c It is possible to use whatever the OS allows as a file name and still import it.
   * - Rule 19.3.1
     - Rule 20.10
     - MISRA C has equivalent which is not considered applicable (ADD6). Rust's macro equivalent are ``concat!`` and ``stringify!``, both of which are generally better behaved. Although for ``stringify!`` still not recommended to not rely on its exact output.
   * - Rule 19.3.2
     - Rule 20.11
     - MISRA C mapping does not apply for equivalent rule.
   * - Rule 19.3.3
     -
     - Constructing new identifiers (like the token-pasting operator used in the rule) is currently not possible using only the stable standard library

       * On nightly there is ``concat_ident`` and ``${concat(...)}`` metavariable

       * There are crates like ``paste`` using proc macros which also enable this.

       However, since both have to create valid identifiers and a macro invocation always contains the non-identifier symbols (e.g. ``!``), this will end up with a compiler error.
   * - Rule 19.3.5
     -
     - This is well defined in rust, see https://lukaswirth.dev/tlborm/decl-macros/patterns/callbacks.html for usecases and a understandable description of the behaviour
   * - Rule 19.6.1
     -
     - Rust does not have a general purpose macro for implementation defined behaviour.
   * - Rule 21.2.1
     -
     - Rust integer and floating point parsing functions (with the FromStr trait) can't cause UB and return Err on overflow or invalid input.
   * - Rule 21.2.2
     -
     - Mapping to rust std: strcat: String::push\_str strchr: str::find strcmp: str::cmp (Ord trait) strcoll: no locale support in rust std strcpy: target String: clear + push\_str or clone\_into, target str: no direct mapping, maybe going through bytes. strcspn: str::find takes a pattern which can be a closure strerror: no mapping to rust strlen: str::len strn-variants: same as original + slicing strpbrk: same as strcspn + slicing strrchr: str::rfind + slicing strspn: str::find + closure with inverted predicate strstr: str::find takes a Pattern which can be a string strtok: str::split strxfrm: no locale support in rust std strtol, strtoll, strtoul: from\_str\_radix strtod, strtof, strtold: FromStr trait fgetwc: Read trait (read\_exact in small buffer or bytes take one) fputwc: Write trait (write\_all with short slice) wcstol, wcstoll, wcstoul, wcstoull, wcstod, wcstof, wcstold (assuming wide str = windows utf16): OsStr::to\_string\_lossy + regular parsing/conversion strtoumax, strtoimax, wcstoumax, wcstoimax: regular versions without max

       Except for locale support all supported in rust std without risk of UB. C++ offers a different API for locale support (locale header) that is not forbidden by this rule, so this does not advise against locale use in general. Therefore it also doesn't map to unsafe rust
   * - Rule 21.2.4
     -
     - Using offset\_of with fields not visible to the callsite is not possible in rust. Use with methods or associated consts is not possible.
   * - Rule 21.6.4
     -
     - Global operator delete maps to the trait "std::alloc::GlobalAlloc", whose deallocation function always requires the layout.
   * - Rule 24.5.1
     -
     - isalnum <-> char::is\_alphanumeric isalpha <-> char::is\_alphabetic islower <-> char::is\_lowercase isupper <-> char::is\_uppercase isdigit <-> char::is\_digit / char::is\_numeric isxdigit <-> char::is\_digit (hex is base 16) iscntrl <-> char::is\_control isgraph <-> char::is\_ascii\_graphic isspace <-> char::is\_whitespace isblank <-> ? What does „blank“ mean? isprint <-> ispunct <-> char::is\_ascii\_punctuation tolower <-> char::to\_lowercase toupper <-> char::to\_uppercase

       Equivalent functions in rust are safe. Missing functions can be implemented in a safe way.
   * - Rule 26.3.1
     -
     - The rust standard library doesn't specialize the layout of the type Vec<bool>, like C++ does.
   * - Rule 28.6.2
     -
     - Rust has no language feature like forwarding references.
   * - Rule 30.0.1
     -
     - This is about the specific issues of these APIs. filesystem operations are supposed to use the filesystem header in C++. As rust has it's own filesystem APIs this does not map. If there is a specific problem with the filesystem APIs in rust that should probably get its own rule.
   * - Rule 30.0.2
     -
     - See mapping of FIO39 in https://coding-guidelines.arewesafetycriticalyet.org/appendices/standards-matrices/cert-c-2016-mapping.html (TLDR: no risk of UB, therefore no mapping)
