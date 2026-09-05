.. SPDX-License-Identifier: MIT OR Apache-2.0
   SPDX-FileCopyrightText: The Coding Guidelines Subcommittee Contributors

.. default-domain:: coding-guidelines

A numeric value shall not be converted to a pointer
===================================================

.. guideline:: A numeric value shall not be converted to a pointer
   :id: gui_PM8Vpf7lZ51U
   :category: <TODO>
   :status: draft
   :release: <TODO>
   :fls: fls_59mpteeczzo
   :decidability: decidable
   :scope: module
   :tags: subset, undefined-behavior

   The ``as`` operator shall not be used with an expression of numeric type as the left operand,
   and any pointer type as the right operand.

   :std:`std::mem::transmute` shall not be used with any numeric type (including floating point types)
   as the argument to the ``Src`` parameter, and any pointer type as the argument to the ``Dst`` parameter.

   In this guideline, "any pointer type" means a raw pointer type or a reference type, matching the
   FLS definition of pointer type :cite:`gui_PM8Vpf7lZ51U:FLS-POINTER-TYPES`.
   Direct transmutation of a numeric value to a function pointer is prohibited by the guideline
   `A numeric value shall not be transmuted to a function pointer`.

   .. rationale::
      :id: rat_YqhEiWTj9z6L
      :status: draft

      A pointer created from an arbitrary arithmetic expression may designate an invalid address,
      including an address that does not point to a valid object, an address that points to an
      object of the wrong type, or an address that is not properly aligned. Use of such a pointer
      to access memory will result in undefined behavior.

      Satisfying those address, type, and alignment conditions is not sufficient to establish that
      memory access is permitted. A well-formed pointer may carry no provenance
      :cite:`gui_PM8Vpf7lZ51U:FLS-WELL-FORMED-POINTER`, and accessing memory through a pointer without
      provenance permitting the access is undefined behavior
      :cite:`gui_PM8Vpf7lZ51U:FLS-POINTER-ACCESS-PROVENANCE`.

      The FLS does not specify the provenance result of every numeric-to-pointer conversion. This
      guideline therefore imposes a conservative subset restriction instead of treating a matching
      numeric address or pointer representation as proof that the result may be dereferenced.

      The ``as`` operator also does not check that the size of the source operand is the same as
      the size of a pointer, which may lead to unexpected results if the address computation was
      originally performed in a differently-sized address space.

      While ``as`` can notionally be used to create a null pointer, the functions
      :std:`core::ptr::null` and :std:`core::ptr::null_mut` are the more idiomatic way to do this.

   .. non_compliant_example::
      :id: non_compl_ex_0ydPk7VENSrA
      :status: draft

      Reconstructing a pointer from a numeric address is noncompliant even when the address was
      obtained from a valid pointer:

      .. rust-example::
        :miri:

        #[allow(dead_code)]
        fn f1(value: &u32) {
          let address = value as * const u32 as usize;
          let _pointer = address as * const u32; // non-compliant
        }
        #
        # fn main() {}

   .. compliant_example::
      :id: compl_ex_oneKuF52yzrx
      :status: draft

      Preserve a pointer as a pointer instead of converting it through a numeric value:

      .. rust-example::

         #[allow(dead_code)]
         fn f2(value: &u32) {
           let _pointer: * const u32 = value;
         }
         #
         # fn main() {}

   .. bibliography::
      :id: bib_PM8Vpf7lZ51U
      :status: draft

      .. list-table::
         :header-rows: 0
         :widths: auto
         :class: bibliography-table

         * - :bibentry:`gui_PM8Vpf7lZ51U:FLS-POINTER-TYPES`
           - The Rust FLS. "Types and Traits - Indirection Types." https://rust-lang.github.io/fls/types-and-traits.html#fls_3qI8FXMsyk0f
         * - :bibentry:`gui_PM8Vpf7lZ51U:FLS-WELL-FORMED-POINTER`
           - The Rust FLS. "Values - Pointer Types." https://rust-lang.github.io/fls/values.html#fls_ffh8mAkebORJ
         * - :bibentry:`gui_PM8Vpf7lZ51U:FLS-POINTER-ACCESS-PROVENANCE`
           - The Rust FLS. "Values - Pointer Types." https://rust-lang.github.io/fls/values.html#fls_c3DaCLQEBpYQ
