.. SPDX-License-Identifier: MIT OR Apache-2.0
   SPDX-FileCopyrightText: The Coding Guidelines Subcommittee Contributors

.. default-domain:: coding-guidelines

A numeric value shall not be converted to an invalid pointer
============================================================

.. guideline:: A numeric value shall not be converted to an invalid pointer
   :id: gui_iv9yCMHRgpE0
   :category: <TODO>
   :status: draft
   :release: <TODO>
   :fls: fls_9wgldua1u8yt
   :decidability: undecidable
   :scope: system
   :tags: defect, undefined-behavior

   An expression of numeric type shall not be converted to a pointer if the resulting pointer
   is incorrectly aligned, does not point to an entity of the referenced type, or is an invalid representation.

   .. rationale::
      :id: rat_OhxKm751axKw
      :status: draft

      The mapping between pointers and integers must be consistent with the addressing structure of the
      execution environment. Issues may arise, for example, on architectures that have a segmented memory model.

      Constructing a pointer from an integer and accessing memory through that pointer are distinct operations.
      A well-formed pointer may carry no provenance :cite:`gui_iv9yCMHRgpE0:FLS-WELL-FORMED-POINTER`
      despite having a plausible machine address. Before the pointer is used to read or write memory, it must
      have provenance permitting that access :cite:`gui_iv9yCMHRgpE0:FLS-POINTER-ACCESS-PROVENANCE` in
      addition to satisfying the alignment, type, and representation conditions above.

      This guideline constrains the result of the conversion. It does not claim that constructing or storing an
      integer-derived pointer, without accessing memory through it, is by itself undefined behavior.

      This guideline remains binding when code operates under an approved deviation from the guideline
      `A numeric value shall not be converted to a pointer`: a deviation permits performing the
      conversion, but does not permit the conversion to produce an invalid pointer.

   .. non_compliant_example::
      :id: non_compl_ex_CkytKjRQezfQ
      :status: draft

      This example makes assumptions about the layout of the address space that do not hold on all platforms.
      The manipulated address may have discarded part of the original address space, and the flag may
      silently interfere with the address value. On platforms where pointers are 64-bits this may have
      particularly unexpected results.

      Assume the numeric-to-pointer conversion below is covered by an approved deviation from the guideline
      `A numeric value shall not be converted to a pointer`.

      The example constructs the resulting pointer but does not access memory through it. It is noncompliant
      because, for some inputs or platforms where its layout assumptions do not hold, the masked and shifted
      address can yield a pointer that is incorrectly aligned, does not point to an entity of the referenced
      type, or has an invalid representation. Such a result violates this guideline. Any later memory access
      would additionally require provenance permitting that access.

      .. rust-example::

        #[allow(dead_code)]
        fn f1(flag: usize, ptr: * const u32) {
          /* ... */
          let mut rep = ptr as usize;
          rep = (rep & 0x7fffff) | (flag << 23);
          let _p2 = rep as * const u32;
        }
        #
        # fn main() {}

   .. compliant_example::
      :id: compl_ex_oBoluiKSvREu
      :status: draft

      This compliant solution uses a struct to provide storage for both the pointer and the flag value.
      This solution is portable to machines of different word sizes, both smaller and larger than 32 bits,
      working even when pointers cannot be represented in any integer type. Keeping the pointer as a pointer
      also preserves its provenance instead of reconstructing it from a numeric address.

      .. rust-example::

        #[allow(dead_code)]
        struct PtrFlag {
          pointer: * const u32,
          flag: u32
        }

        #[allow(dead_code)]
        fn f2(flag: u32, ptr: * const u32) {
          let _ptrflag = PtrFlag {
            pointer: ptr,
            flag: flag
          };
          /* ... */
        }
        #
        # fn main() {}

   .. bibliography::
      :id: bib_iv9yCMHRgpE0
      :status: draft

      .. list-table::
         :header-rows: 0
         :widths: auto
         :class: bibliography-table

         * - :bibentry:`gui_iv9yCMHRgpE0:FLS-WELL-FORMED-POINTER`
           - The Rust FLS. "Values - Pointer Types." https://rust-lang.github.io/fls/values.html#fls_ffh8mAkebORJ
         * - :bibentry:`gui_iv9yCMHRgpE0:FLS-POINTER-ACCESS-PROVENANCE`
           - The Rust FLS. "Values - Pointer Types." https://rust-lang.github.io/fls/values.html#fls_c3DaCLQEBpYQ
