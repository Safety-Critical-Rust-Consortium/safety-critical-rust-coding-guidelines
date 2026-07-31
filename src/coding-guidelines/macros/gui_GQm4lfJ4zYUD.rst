Avoid unused macros
===================

.. guideline:: Avoid Unused Macros
    :id: gui_GQm4lfJ4zYUD
    :category: advisory
    :status: draft
    :release: unclear
    :fls: fls_83182bfa9uqb
    :decidability: decidable
    :scope: system
    :tags: maintainability

    Avoid defining macros that are never used.

    .. rationale::
        :id: rat_h36jR1v3hTnx
        :status: draft

        Ensuring that all code is used reduces potential mistakes in unfinished code.

    .. non_compliant_example::
        :id: non_compl_ex_1dv2kGST217Z
        :status: draft

        The macro `never_used` is not used.

        .. rust-example::
            :no_run:

            #[allow(unused_macros)]
            macro_rules! never_used {
                () => {};
            }

            fn main() {
            }


    .. compliant_example::
        :id: compl_ex_gtdFrUPXYBG2
        :status: draft

        The `used_macro` is exported and used.

        .. rust-example::

            macro_rules! used_macro {
            ($t:expr) => {
                println!("MACRO TEXT: {}", $t);
                }
            }

            fn main() {
            used_macro!("I am used, therefore I am.");
            }

.. bibliography::
      :id: bib_STH4njMLYuZ
      :status: draft

      .. list-table::
         :header-rows: 0
         :widths: auto
         :class: bibliography-table

         * - :bibentry:`gui_GQm4lfJ4zYUD:RUSTC-LINT`
           - Rust C lints. "UNUSED_MACROS" https://doc.rust-lang.org/stable/nightly-rustc/rustc_lint/builtin/static.UNUSED_MACROS.html

         * - :bibentry:`gui_GQm4lfJ4zYUD:MISRA-C`
           - MISRA C. "Rule 2.5" https://misra.org.uk/product/misra-c2025/
