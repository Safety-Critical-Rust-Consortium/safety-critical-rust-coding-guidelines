.. SPDX-License-Identifier: MIT OR Apache-2.0
   SPDX-FileCopyrightText: The Coding Guidelines Subcommittee Contributors

.. default-domain:: coding-guidelines

A numeric value shall not be transmuted to a function pointer
=============================================================

.. guideline:: A numeric value shall not be transmuted to a function pointer
   :id: gui_gghCZVhoRV8Z
   :category: required
   :status: draft
   :release: <TODO>
   :fls: fls_52thmi9hnoks
   :decidability: decidable
   :scope: module
   :tags: subset, undefined-behavior

   :std:`std::mem::transmute` shall not be used with any numeric type (including floating point types)
   as the argument to the ``Src`` parameter, and any function pointer type as the argument to the
   ``Dst`` parameter.

   .. rationale::
      :id: rat_71j2Ud06kthz
      :status: draft

      An all-zero numeric representation can produce a null function pointer and violate the function-pointer
      validity invariant at construction :cite:`gui_gghCZVhoRV8Z:FLS-FUNCTION-POINTER-TYPES`. A nonzero
      representation does not violate that invariant merely because it came from a numeric value, but non-nullness
      alone does not establish that it designates a function callable through the destination function pointer type.

      In particular, the FLS defines calling a function with an ABI other than the ABI with which it was defined as
      undefined behavior :cite:`gui_gghCZVhoRV8Z:FLS-CALL-EXPRESSIONS`. A numeric value cannot establish that the
      address designates a function callable through the destination function pointer type. This guideline therefore
      imposes a conservative subset restriction on direct numeric-to-function-pointer transmutation.

      The ``as`` operator cannot directly convert a numeric value to a function pointer. Direct numeric-to-raw-pointer
      ``as`` casts and numeric-to-pointer :std:`std::mem::transmute` operations are prohibited by the guideline
      `A numeric value shall not be converted to a pointer`.

   .. non_compliant_example::
      :id: non_compl_ex_jg56Jyx1KbkE
      :status: draft

      Directly transmuting a numeric value to a function pointer is noncompliant, even if the resulting pointer is
      never called:

      .. rust-example::
         :miri:

         #[allow(dead_code)]
         fn f1(address: usize) {
           unsafe {
             let _function = std::mem::transmute::<usize, fn()>(address); // non-compliant
           }
         }
         #
         # fn main() {}

   .. compliant_example::
      :id: compl_ex_8S7Xw4sUk6kP
      :status: draft

      Obtain a function pointer from a function item instead of fabricating one from a numeric value:

      .. rust-example::

         fn target() {}

         fn main() {
           let _handler: fn() = target;
         }

   .. bibliography::
      :id: bib_gghCZVhoRV8Z
      :status: draft

      .. list-table::
         :header-rows: 0
         :widths: auto
         :class: bibliography-table

         * - :bibentry:`gui_gghCZVhoRV8Z:FLS-FUNCTION-POINTER-TYPES`
           - The Rust FLS. "Types and Traits - Indirection Types - Function Pointer Types." https://rust-lang.github.io/fls/types-and-traits.html#fls_52thmi9hnoks
         * - :bibentry:`gui_gghCZVhoRV8Z:FLS-CALL-EXPRESSIONS`
           - The Rust FLS. "Expressions - Call Expressions." https://rust-lang.github.io/fls/expressions.html#fls_5yeq4oah58dl
