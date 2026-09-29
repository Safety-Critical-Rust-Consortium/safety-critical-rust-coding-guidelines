Rust Cross Reference with CERT-C 2016
=======================================

The following tables provide a cross reference between the CERT C 2016 guidelines and their applicability to Rust. The
first table covers guidelines that are applicable to Rust in general, while the second table covers additional
guidelines that are applicable in the presence of unsafe code. The third table lists guidelines that are not applicable
to Rust.

The mappings use the shared :ref:`standards-matrix-coverage`.


Table 1 – Guidelines applicable to Rust in general (safe Rust, no unsafe code present)
--------------------------------------------------------------------------------------

.. list-table::
   :widths: 14 14 14 14 14
   :header-rows: 1

   * - Guideline
     - Title
     - Category
     - Safety Critical rust Rule
     - Comment
   * - `FLP37 <https://wiki.sei.cmu.edu/confluence/display/c/FLP37-C.+Do+not+use+object+representations+to+compare+floating-point+values>`__
     - Do not use object representations to compare floating-point
       values
     - 
     - 
     - It might not be immediately obvious where this might be done on
       purpose. It is certainly not something one would imagine
       happening in a self-contained system that’s using floating point
       numbers. However, **when receiving raw floating point data**, it
       can be extremely tempting to “just compare the bits”. What’s
       worse is that **this approach would work for some values**, which
       might mask its lack of correctness. For completeness, it would be
       good to mention examples of FP values with different encodings
       that however compare equal under the standard. The simplest one
       here is, I think, ``0`` v/s ``-0``, which would bitwise compare
       different and yet are considered equal under the IEEE FP
       standard. **Bonus idea:** we might want to have a float-equality
       guideline with regards to ``NaN``, since ``NaN != NaN`` even when
       the encoding is the same. For answering the question of “is this
       value ``NaN``?”, we have the
       ```is_nan`` <https://doc.rust-lang.org/std/primitive.f32.html?search=is_nan>`__
       method.
   * - `DCL39 <https://wiki.sei.cmu.edu/confluence/display/c/DCL39-C.+Avoid+information+leakage+when+passing+a+structure+across+a+trust+boundary>`__
     - Avoid information leakage when passing a structure across a trust
       boundary
     - 
     - 
     - It seems to be technically possible to achieve, using Unsafe.
       Zulip thread of this discussion: `How should padding bits be
       erased for
       sending? <https://rust-lang.zulipchat.com/#narrow/channel/136281-t-opsem/topic/How.20should.20padding.20bits.20be.20erased.20for.20sending.3F/with/564800067>`__\ The
       important issue seems to be that of copying into the untrusted
       buffer without copying sensitive data that may lie in the
       uninitialized bits of the copied struct.For structs and enums,
       this seems to be solvable by making a type which copies
       everything except for the padding bits inside of it.For unions,
       one might want to be REALLY SURE, and hopefully prove, that
       you’re not copying your padding. Might be impossible to safely
       send unions.\ *One might want also to zero-out sensitive memory
       in their own processes, such that nothing sensitive is left
       behind after they end.* **That’s outside the scope of our work.**
       *Zulip thread on this:* `Are bits erased on drop? If not, how can
       I ensure they
       are? <https://rust-lang.zulipchat.com/#narrow/channel/122651-general/topic/Are.20bits.20erased.20on.20drop.3F.20If.20not.2C.20how.20can.20I.20ensure.20they.20are.3F/with/564800542>`__
   * - `INT36 <https://wiki.sei.cmu.edu/confluence/display/c/INT36-C.+Converting+a+pointer+to+integer+or+integer+to+pointer>`__
     - Converting a pointer to integer or integer to pointer
     - 
     - 
     - With modifications:- ptr2int: considered to be relatively
       unimportant- int2ptr: cautioned against\ **Pointer Provenance**
       plays a role in this.\ *Also, see:* `transmute: caution against
       int2ptr
       transmutation <http://github.com/rust-lang/rust/pull/122379>`__\ May
       deserve scrutiny for possible unsafe-heavy treatment
   * - `CON40 <https://wiki.sei.cmu.edu/confluence/display/c/CON40-C.+Do+not+refer+to+an+atomic+variable+twice+in+an+expression>`__
     - Do not refer to an atomic variable twice in an expression
     - 
     - 
     - 
   * - `CON36 <https://wiki.sei.cmu.edu/confluence/display/c/CON36-C.+Wrap+functions+that+can+spuriously+wake+up+in+a+loop>`__
     - Wrap functions that can spuriously wake up in a loop
     - 
     - 
     - This directly maps to the usage of
       ```std::sync::Condvar`` <https://doc.rust-lang.org/std/sync/struct.Condvar.html>`__,
       in particular while using its
       ```wait`` <https://doc.rust-lang.org/std/sync/struct.Condvar.html#method.wait>`__
       and
       ```wait_timeout`` <https://doc.rust-lang.org/std/sync/struct.Condvar.html#method.wait_timeout>`__
       methods.To correctly wrap these spurious wake-ups in a loop, the
       methods
       ```wait_while`` <https://doc.rust-lang.org/std/sync/struct.Condvar.html#method.wait_while>`__
       and
       ```wait_timeout_while`` <https://doc.rust-lang.org/std/sync/struct.Condvar.html#method.wait_timeout_while>`__
       are respectively provided, and should probably be recommended in
       their place.
   * - `EXP40 <https://wiki.sei.cmu.edu/confluence/display/c/EXP40-C.+Do+not+modify+constant+objects>`__
     - Do not modify constant objects
     - 
     - 
     - ``const`` items can’t be modified - they are actually inlined at
       every point of usage, so modifying them wouldn’t do a thing
       anyways. So this is not about ``const`` in the case of Rust.On
       the other hand, ``static`` items can be modified, but only in
       ``unsafe`` code. And this is by design - some things are meant to
       be “global items with special case mutability”A difference must
       be made, however, with regards to ``static`` and ``static mut``
       variables, because as expressed
       `here <https://github.com/rust-lang/unsafe-code-guidelines/issues/269>`__,
       the latter is incredibly prone to UB. ``static`` variables can be
       used with a lot more ease (still with plenty of caution!), using
       `the interior mutability
       pattern <https://doc.rust-lang.org/book/ch15-05-interior-mutability.html>`__,
       covering the vast majority of use-cases for global mutable
       state.\ *My current line of thought is that ``static mut`` should
       be forbidden as either a Mandatory rule (i.e. with no exceptions)
       or a Required rule with well-documented reasoning about its
       safety. Remember:* `usage of ``static mut`` very easily results
       in
       UB. <https://doc.rust-lang.org/nightly/edition-guide/rust-2024/static-mut-references.html#safe-references>`__\ \ *As
       for ``static``, I think I would like us to have an Advisory rule
       recommending against them. Hopefully, such a rule would show
       examples of how to use ``static`` safely.*\  **Paired with
       STR30**
   * - `STR30 <https://wiki.sei.cmu.edu/confluence/display/c/STR30-C.+Do+not+attempt+to+modify+string+literals>`__
     - Do not attempt to modify string literals
     - 
     - 
     - Treat as **merged with EXP40** for Rust mapping purposes
   * - `INT30 <https://wiki.sei.cmu.edu/confluence/display/c/INT30-C.+Ensure+that+unsigned+integer+operations+do+not+wrap>`__
     - Ensure that integer operations do not wrap
     - 
     - 
     - Already implemented; still review mapping/category
   * - `INT33 <https://wiki.sei.cmu.edu/confluence/display/c/INT33-C.+Ensure+that+division+and+remainder+operations+do+not+result+in+divide-by-zero+errors>`__
     - Ensure that division and remainder operations do not result in
       divide-by-zero errors
     - 
     - 
     - Already implemented; still review mapping/category
   * - `ARR30 <https://wiki.sei.cmu.edu/confluence/display/c/ARR30-C.+Do+not+form+or+use+out-of-bounds+pointers+or+array+subscripts>`__
     - Do not form or use out-of-bounds pointers or array subscripts
     - 
     - 
     - In Safe Rust:- Direct addressing will panic if OOB-
       arr.get(index) will return None if OOBIn Unsafe Rust:-
       arr.get_unchecked(index) is UB if OOB.So, I’d say out-of-bound
       indexing should be either prevented or handled properly.If using
       Unsafe indexing, it should be formally validated.
   * - `FIO45 <https://wiki.sei.cmu.edu/confluence/display/c/FIO45-C.+Avoid+TOCTOU+race+conditions+while+accessing+files>`__
     - Avoid TOCTOU race conditions while accessing files
     - 
     - 
     - *Rationale:*
       ```std::fs`` <https://doc.rust-lang.org/std/fs/index.html#time-of-check-to-time-of-use-toctou>`__
       `explicitly talks about
       TOCTOU <https://doc.rust-lang.org/std/fs/index.html#time-of-check-to-time-of-use-toctou>`__
       *and how to avoid it.*
   * - `FLP30 <https://wiki.sei.cmu.edu/confluence/display/c/FLP30-C.+Do+not+use+floating-point+variables+as+loop+counters>`__
     - Do not use floating-point variables as loop counters
     - 
     - 
     - 
   * - `INT31 <https://wiki.sei.cmu.edu/confluence/display/c/INT31-C.+Ensure+that+integer+conversions+do+not+result+in+lost+or+misinterpreted+data>`__
     - Ensure that integer conversions do not result in lost or
       misinterpreted data
     - 
     - 
     - Already being worked in #185; still review mapping/category
   * - `FLP32 <https://wiki.sei.cmu.edu/confluence/display/c/FLP32-C.+Prevent+or+detect+domain+and+range+errors+in+math+functions>`__
     - Prevent or detect domain and range errors in math functions
     - 
     - 
     - 
   * - `ENV33 <https://wiki.sei.cmu.edu/confluence/display/c/ENV33-C.+Do+not+call+system%28%29>`__
     - Do not call system()
     - 
     - 
     - The mapping is not exact (it doesn’t involve system()):If running
       commands, their input must always be sanitized, and their
       behavior should be made portable.There is `a Clippy
       lint <https://rust-lang.github.io/rust-clippy/master/index.html?search=command#suspicious_command_arg_space>`__
       that touches on this topic. We probably want a set of rules to
       address how system commands may be called.
   * - `MSC41 <https://wiki.sei.cmu.edu/confluence/display/c/MSC41-C.+Never+hard+code+sensitive+information>`__
     - Never hard code sensitive information
     - 
     - 
     - 
   * - `MEM31 <https://wiki.sei.cmu.edu/confluence/display/c/MEM31-C.+Free+dynamically+allocated+memory+when+no+longer+needed>`__
     - Free dynamically allocated memory when no longer needed
     - 
     - 
     - The Rust compiler mostly enforces this automatically.Important
       exceptions in Safe Rust are
       ```std::rc::Rc`` <https://doc.rust-lang.org/std/rc/struct.Rc.html>`__/```std::sync::Arc`` <https://doc.rust-lang.org/std/sync/struct.Arc.html>`__
       cycles, which the user should avoid using the corresponding
       ```std::rc::Weak`` <https://doc.rust-lang.org/std/rc/struct.Weak.html>`__
       and
       ```std::sync::Weak`` <https://doc.rust-lang.org/std/sync/struct.Weak.html>`__.Memory
       leaks in Rust are relatively easy to avoid (compared to manual
       ``malloc`` and ``free`` in C), but they are nonetheless still
       possible. Furthermore, memory leaks are considered safe in
       Rust.Much like the original rule, our mapping would describe a
       defect of low severity, as their worst possible consequence is a
       Denial of Service due to memory exhaustion.
   * - `INT32 <https://wiki.sei.cmu.edu/confluence/display/c/INT32-C.+Ensure+that+operations+on+signed+integers+do+not+result+in+overflow>`__
     - Ensure that operations on signed integers do not result in
       overflow
     - 
     - 
     - Already implemented; still review mapping/category
   * - `INT34 <https://wiki.sei.cmu.edu/confluence/display/c/INT34-C.+Do+not+shift+an+expression+by+a+negative+number+of+bits+or+by+greater+than+or+equal+to+the+number+of+bits+that+exist+in+the+operand>`__
     - Do not shift an expression by a negative number of bits or by
       greater than or equal to the number of bits that exist in the
       operand
     - 
     - 
     - Already implemented; still review mapping/category
   * - `CON33 <https://wiki.sei.cmu.edu/confluence/display/c/CON33-C.+Avoid+race+conditions+when+using+library+functions>`__
     - Avoid race conditions when using library functions
     - 
     - 
     - 
   * - `CON41 <https://wiki.sei.cmu.edu/confluence/display/c/CON41-C.+Wrap+functions+that+can+fail+spuriously+in+a+loop>`__
     - Wrap functions that can spuriously fail in a loop
     - 
     - 
     - 
   * - `ARR37 <https://wiki.sei.cmu.edu/confluence/display/c/ARR37-C.+Do+not+add+or+subtract+an+integer+to+a+pointer+to+a+non-array+object>`__
     - Do not add or subtract an integer to a pointer to a non-array
       object
     - 
     - 
     - 
   * - `FLP34 <https://wiki.sei.cmu.edu/confluence/display/c/FLP34-C.+Ensure+that+floating-point+conversions+are+within+range+of+the+new+type>`__
     - Ensure that floating-point conversions are within range of the
       new type
     - 
     - 
     - 
   * - `FLP36 <https://wiki.sei.cmu.edu/confluence/display/c/FLP36-C.+Preserve+precision+when+converting+integral+values+to+floating-point+type>`__
     - Preserve precision when converting integral values to
       floating-point type
     - 
     - 
     - 
   * - `FIO42 <https://wiki.sei.cmu.edu/confluence/display/c/FIO42-C.+Close+files+when+they+are+no+longer+needed>`__
     - Close files when they are no longer needed
     - 
     - 
     - This is a good precept for life, I guess.In Rust, handling of
       such resources is a lot easier since their Drop implementation
       should close them automatically.It’s still good to keep in mind,
       and not make a file e.g. have the ``'static`` lifetime if that’s
       not necessary.
   * - `CON38 <https://wiki.sei.cmu.edu/confluence/display/c/CON38-C.+Preserve+thread+safety+and+liveness+when+using+condition+variables>`__
     - Preserve thread safety and liveness when using condition
       variables
     - 
     - 
     - So far, the consensus is to make the following recommendations:-
       *Consider not using ``Condvar`` if at all possible.*\ - *If using
       ``Condvar`` and liveness is critical, consider using
       ``notify_all`` instead of ``notify_one``.*\ Zulip discussion:
       `Recommending ``Condvar::notify_all`` instead of
       ``notify_one``? <https://rust-lang.zulipchat.com/#narrow/channel/122651-general/topic/Recommending.20.60Condvar.3A.3Anotify_all.60.20instead.20of.20.60notify_one.60.3F/with/572488048>`__\ Higher-policy
       discussion expected
   * - `MSC32 <https://wiki.sei.cmu.edu/confluence/display/c/MSC32-C.+Properly+seed+pseudorandom+number+generators>`__
     - Properly seed pseudorandom number generators
     - 
     - 
     - 
   * - `MEM34 <https://wiki.sei.cmu.edu/confluence/display/c/MEM34-C.+Only+free+memory+allocated+dynamically>`__
     - Only free memory allocated dynamically
     - 
     - 
     - 
   * - `CON35 <https://wiki.sei.cmu.edu/confluence/display/c/CON35-C.+Avoid+deadlock+by+locking+in+a+predefined+order>`__
     - Avoid deadlock by locking in a predefined order
     - 
     - 
     - 

Table 2 – Guidelines applicable to Rust in the presence of unsafe code
----------------------------------------------------------------------

.. list-table::
   :widths: 14 14 14 14 14
   :header-rows: 1

   * - Guideline
     - Title
     - Category
     - Safety Critical rust Rule
     - Comment
   * - `EXP39 <https://wiki.sei.cmu.edu/confluence/display/c/EXP39-C.+Do+not+access+a+variable+through+a+pointer+of+an+incompatible+type>`__
     - Do not access a variable through a pointer of an incompatible
       type
     - 
     - 
     - 
   * - `CON32 <https://wiki.sei.cmu.edu/confluence/display/c/CON32-C.+Prevent+data+races+when+accessing+bit-fields+from+multiple+threads>`__
     - Prevent data races when accessing bit-fields from multiple
       threads
     - 
     - 
     - 
   * - `CON43 <https://wiki.sei.cmu.edu/confluence/display/c/CON43-C.+Do+not+allow+data+races+in+multithreaded+code>`__
     - Do not allow data races in multithreaded code
     - 
     - 
     - Treat as **paired with CON32** in Rust, as their requirements are
       the same
   * - `ARR36 <https://wiki.sei.cmu.edu/confluence/display/c/ARR36-C.+Do+not+subtract+or+compare+two+pointers+that+do+not+refer+to+the+same+array>`__
     - Do not subtract or compare two pointers that do not refer to the
       same array
     - 
     - 
     - 
   * - `MEM30 <https://wiki.sei.cmu.edu/confluence/display/c/MEM30-C.+Do+not+access+freed+memory>`__
     - Do not access freed memory
     - 
     - 
     - 
   * - `EXP34 <https://wiki.sei.cmu.edu/confluence/display/c/EXP34-C.+Do+not+dereference+null+pointers>`__
     - Do not dereference null pointers
     - 
     - 
     - 
   * - `DCL30 <https://wiki.sei.cmu.edu/confluence/display/c/DCL30-C.+Declare+objects+with+appropriate+storage+durations>`__
     - Declare objects with appropriate storage durations
     - 
     - 
     - 
   * - `EXP42 <https://wiki.sei.cmu.edu/confluence/display/c/EXP42-C.+Do+not+compare+padding+data>`__
     - Do not compare padding data
     - 
     - 
     - 
   * - `ENV31 <https://wiki.sei.cmu.edu/confluence/display/c/ENV31-C.+Do+not+rely+on+an+environment+pointer+following+an+operation+that+may+invalidate+it>`__
     - Do not rely on an environment pointer following an operation that
       may invalidate it
     - 
     - 
     - Recently moved into the unsafe bucket This interaction maps to
       Rust through the
       ```std::env::set_var`` <https://doc.rust-lang.org/std/env/fn.set_var.html>`__
       and
       ```std::env::remove_var`` <https://doc.rust-lang.org/std/env/fn.remove_var.html>`__
       APIs.In Unix, they are **only safe to use in single-threaded
       programs**. Such is the reality of those system APIs at the
       moment of writing (28-Feb-2026).The rule would forbid both APIs
       in multithreaded code running on Unix systems.
   * - `EXP33 <https://wiki.sei.cmu.edu/confluence/display/c/EXP33-C.+Do+not+read+uninitialized+memory>`__
     - Do not read uninitialized memory
     - 
     - 
     - *Rationale: it’s UB in Rust*
   * - `MEM36 <https://wiki.sei.cmu.edu/confluence/display/c/MEM36-C.+Do+not+modify+the+alignment+of+objects+by+calling+realloc%28%29>`__
     - Do not modify the alignment of objects by calling realloc()
     - 
     - 
     - 
   * - `CON34 <https://wiki.sei.cmu.edu/confluence/display/c/CON34-C.+Declare+objects+shared+between+threads+with+appropriate+storage+durations>`__
     - Declare objects shared between threads with appropriate storage
       durations
     - 
     - 
     - 
   * - `EXP36 <https://wiki.sei.cmu.edu/confluence/display/c/EXP36-C.+Do+not+cast+pointers+into+more+strictly+aligned+pointer+types>`__
     - Do not cast pointers into more strictly aligned pointer types
     - 
     - 
     - 
   * - `MEM35 <https://wiki.sei.cmu.edu/confluence/display/c/MEM35-C.+Allocate+sufficient+memory+for+an+object>`__
     - Allocate sufficient memory for an object
     - 
     - 
     - 

Table 3 – Guideline rules that are not applicable to Rust
---------------------------------------------------------

.. list-table::
   :widths: 14 14 14 14 14
   :header-rows: 1

   * - Guideline
     - Title
     - Category
     - Safety Critical rust Rule
     - Comment
   * - `PRE31 <https://wiki.sei.cmu.edu/confluence/display/c/PRE31-C.+Avoid+side+effects+in+arguments+to+unsafe+macros>`__
     - Avoid side effects in arguments to unsafe macros
     - 
     - 
     - **Context**\  *In C, “unsafe macro” means a macro that evaluates
       one of its parameters more than once or not at all. Doing so with
       side effects then means that those side effects are triggered
       either more than once, or not at all.*\ C macros make using this
       kind of pattern safely very hard.In Rust, this is not the case,
       and there are multiple examples of macros that use this pattern
       on purpose and successfully.There are multiple different use
       cases for this, in fact, as explained in `this comment on
       Zulip <https://rust-lang.zulipchat.com/#narrow/channel/122651-general/topic/How.20common.20are.20macros.20that.20evaluate.20side.20effects.20twice.3F/near/564929315>`__.
       Furthermore, if no side effecting is required, then the writer of
       the macro can enforce this using ``const`` blocks, as is
       explained in the `comment right
       after <https://rust-lang.zulipchat.com/#narrow/channel/122651-general/topic/How.20common.20are.20macros.20that.20evaluate.20side.20effects.20twice.3F/near/564929413>`__.There
       is no magic feature in Rust to stop a macro from expanding a
       side-effecting expression multiple times. However, doing so
       requires to be a lot more explicit about it. Therefore, if such a
       macro invocation is encountered in the wild, then chances are
       that the user meant to do exactly that.\ *Zulip thread:* `Macros
       and insertion of side-effecting
       metavariables <https://rust-lang.zulipchat.com/#narrow/channel/404510-wg-macros/topic/Macros.20and.20insertion.20of.20side-effecting.20metavariables/with/564129698>`__
       Review current reasoning for macro applicability
   * - `EXP30 <https://wiki.sei.cmu.edu/confluence/display/c/EXP30-C.+Do+not+depend+on+the+order+of+evaluation+for+side+effects>`__
     - Do not depend on the order of evaluation for side effects
     - 
     - 
     - Unlike for C, the evaluation order is fully defined in Rust:
       `expressions -> expression
       precedence <https://doc.rust-lang.org/reference/expressions.html#expression-precedence>`__\ Thus,
       this rule isn’t really needed. At least, not with the same
       UB-stopping urgency that it is needed for in C.\ *Extra notes:
       there is a restriction lint that touches on this topic, as a
       precedent:*
       ```mixed_read_write_in_expression`` <https://rust-lang.github.io/rust-clippy/master/index.html?search=evaluation#mixed_read_write_in_expression>`__
   * - `EXP32 <https://wiki.sei.cmu.edu/confluence/display/c/EXP32-C.+Do+not+access+a+volatile+object+through+a+nonvolatile+reference>`__
     - Do not access a volatile object through a nonvolatile reference
     - 
     - 
     - Volatile is specific to C in this case.Furthermore, a mismatch
       like this would be bound by the rules of the type system, and
       thus be caught unless the user were to be using transmutation.
       Rules about transmutation, however, are not a map of this rule
       but they are rather their own thing.
   * - `ARR39 <https://wiki.sei.cmu.edu/confluence/display/c/ARR39-C.+Do+not+add+or+subtract+a+scaled+integer+to+a+pointer>`__
     - Do not add or subtract a scaled integer to a pointer
     - 
     - 
     - Pointer arithmetic is done through APIs in Rust, `all of
       which <https://doc.rust-lang.org/std/primitive.pointer.html>`__
       mention up-front that their ``count: usize`` parameter is in
       units of the underlying type ``T``. Even the name strongly
       indicates that it’s a **count**, and not a specific length.If the
       ARR39 kind of pattern proves to be a problem, a rule can be made
       about it. As far as I can tell, however, it is not.
   * - `FIO32 <https://wiki.sei.cmu.edu/confluence/display/c/FIO32-C.+Do+not+perform+operations+on+devices+that+are+only+appropriate+for+files>`__
     - Do not perform operations on devices that are only appropriate
       for files
     - 
     - 
     - **Context**\  *In C, those APIs might block (the current thread)
       if the files being open correspond to devices (files under
       ``/dev/``). This in turn can lead to a Denial of Service, by
       effectively blocking the system.* The APIs present in
       ```std::fs`` <https://doc.rust-lang.org/std/fs/>`__ are quite a
       bit different from the ones present in C.Some functions in this
       module may block:- Attempting to take a filesystem lock,- Calling
       ``Read::read`` (might block waiting for data), and -
       ``Write::write`` (might block waiting for data to be
       written).However, a rule that restricts the use of blocking
       actions over a filesystem is quite different from FIO32. Thus, I
       don’t believe this maps to Rust. Related filesystem guidance may
       instead belong near #392
   * - `FIO46 <https://wiki.sei.cmu.edu/confluence/display/c/FIO46-C.+Do+not+access+a+closed+file>`__
     - Do not access a closed file
     - 
     - 
     - This is guaranteed in Rust already by the fact that closing a
       file consumes the variable, invalidating any future accesses to
       it.\ *Unsafe Rust, as always, could get away with doing something
       like this regardless, but that would be UB and* **should be
       covered by a different guideline** *(something along the lines of
       “don’t extend lifetimes beyond their valid range”*
   * - `ENV34 <https://wiki.sei.cmu.edu/confluence/display/c/ENV34-C.+Do+not+store+pointers+returned+by+certain+functions>`__
     - Do not store pointers returned by certain functions
     - 
     - 
     - Live References cannot be invalidated in Rust.\ *Implementors of
       such libraries in Unsafe Rust must take care to not invalidate
       the references they create. This would be UB. It would always
       violate the memory model. But the rule to enforce this lies
       outside of the context of ENV34. It’s a more general rule that
       must be followed.*
   * - `CON37 <https://wiki.sei.cmu.edu/confluence/display/c/CON37-C.+Do+not+call+signal%28%29+in+a+multithreaded+program>`__
     - Do not call signal() in a multithreaded program
     - 
     - 
     - Rust doesn’t provide support for signal handling in ``std``.
       Details as to why can be seen
       `here <https://github.com/rust-lang/rfcs/issues/1368>`__.Since
       this feature is not supported in Rust, the rule doesn’t
       apply.\ *That being said, there are crates which provide signal
       handling utilities. Some are mentioned in the linked thread
       above. Dear reader, use those crates at your own discretion.*
   * - `MSC30 <https://wiki.sei.cmu.edu/confluence/display/c/MSC30-C.+Do+not+use+the+rand%28%29+function+for+generating+pseudorandom+numbers>`__
     - Do not use the rand() function for generating pseudorandom
       numbers
     - 
     - 
     - `The APIs for generating pseudorandom numbers in core and
       std <https://doc.rust-lang.org/std/random/index.html>`__ are
       currently nightly-only.\ *I don’t know if it was RNG, but IIRC
       something like it from the stdlib was discouraged in Rust as
       well, due to it not being collision resistant. I’m pretty sure it
       was a hash function or something.*
   * - `STR31 <https://wiki.sei.cmu.edu/confluence/display/c/STR31-C.+Guarantee+that+storage+for+strings+has+sufficient+space+for+character+data+and+the+null+terminator>`__
     - Guarantee that storage for strings has sufficient space for
       character data and the null terminator
     - 
     - 
     - Strings are not null-terminated in Rust and their storage space
       is guaranteed
   * - `DCL40 <https://wiki.sei.cmu.edu/confluence/display/c/DCL40-C.+Do+not+create+incompatible+declarations+of+the+same+function+or+object>`__
     - Do not create incompatible declarations of the same function or
       object
     - 
     - 
     - *Rationale: doing this is impossible in Rust.*
   * - `PRE30 <https://wiki.sei.cmu.edu/confluence/display/c/PRE30-C.+Do+not+create+a+universal+character+name+through+concatenation>`__
     - Do not create a universal character name through concatenation
     - 
     - 
     - *Rationale: it’s just very specific to C*
   * - `DCL38 <https://wiki.sei.cmu.edu/confluence/display/c/DCL38-C.+Use+the+correct+syntax+when+declaring+a+flexible+array+member>`__
     - Use the correct syntax when declaring a flexible array member
     - 
     - 
     - The rule is about “using the standardized syntax for this
       feature, instead of relying on Undefined Behavior and a
       compiler-specific, non-standardized syntax”.Such a suggestion
       makes no sense in Rust, since there is only one compiler and its
       syntax is the only one available. Correct syntax can compile;
       incorrect syntax cannot.
   * - `EXP35 <https://wiki.sei.cmu.edu/confluence/display/c/EXP35-C.+Do+not+modify+objects+with+temporary+lifetime>`__
     - Do not modify objects with temporary lifetime
     - 
     - 
     - *Rationale: the borrow checker eliminates this problem*
   * - `EXP43 <https://wiki.sei.cmu.edu/confluence/display/c/EXP43-C.+Avoid+Undefined+Behavior+when+using+restrict-qualified+pointers>`__
     - Avoid Undefined Behavior when using restrict-qualified pointers
     - 
     - 
     - The borrow checker gives us correct-by-construction restrict
       qualifications in codegen. Basically, “restrict” is part of the
       type system, and type checking (in particular borrow checking)
       enforces that its rules are always abided by.
   * - `ARR32 <https://wiki.sei.cmu.edu/confluence/display/c/ARR32-C.+Ensure+size+arguments+for+variable+length+arrays+are+in+a+valid+range>`__
     - Ensure size arguments for variable length arrays are in a valid
       range
     - 
     - 
     - *Rationale: VLAs are not a thing in Rust*
   * - `ARR38 <https://wiki.sei.cmu.edu/confluence/display/c/ARR38-C.+Guarantee+that+library+functions+do+not+form+invalid+pointers>`__
     - Guarantee that library functions do not form invalid pointers
     - 
     - 
     - The rule basically asks the user that, whenever they call a
       function that receives a pointer to an array and a length, that
       said length doesn’t go outside the bounds of the array (which
       would form an invalid pointer)In Safe Rust, this is handled by
       bounds checks, and in the mapping of ARR30 we’re already handling
       that.In Unsafe Rust, doing this is to break the Safety Contract
       of the API we’re calling, which `is getting its own
       rule. <https://github.com/Safety-Critical-Rust-Consortium/safety-critical-rust-coding-guidelines/issues/337>`__
       and is outside the mapping of this ARR38 (this rule) Recently
       moved out of the applicable bucket
   * - `STR32 <https://wiki.sei.cmu.edu/confluence/display/c/STR32-C.+Do+not+pass+a+non-null-terminated+character+sequence+to+a+library+function+that+expects+a+string>`__
     - Do not pass a non-null-terminated character sequence to a library
       function that expects a string
     - 
     - 
     - *Rationale: strings are not null-terminated in Rust*
   * - `FIO34 <https://wiki.sei.cmu.edu/confluence/display/c/FIO34-C.+Distinguish+between+characters+read+from+a+file+and+EOF+or+WEOF>`__
     - Distinguish between characters read from a file and EOF or WEOF
     - 
     - 
     - See the
       `Read <https://doc.rust-lang.org/std/io/trait.Read.html>`__
       trait. EOF / WEOF cannot be acquired from them.As long as file
       reading operations are done through the Read trait, this should
       not be a concern.
   * - `FIO37 <https://wiki.sei.cmu.edu/confluence/display/c/FIO37-C.+Do+not+assume+that+fgets%28%29+or+fgetws%28%29+returns+a+nonempty+string+when+successful>`__
     - Do not assume that fgets() or fgetws() returns a nonempty string
       when successful
     - 
     - 
     - This rule comes from the need to properly handle errors found
       during the execution of ``fgets()`` and ``fgetws()``. Errors in
       those functions are reported in a way whose proper handling
       cannot be enforced by the compiler.Fallible APIs in Rust return
       values of the enum ``Result<T, E>``, whose error case must be
       properly handled, in order for the program to compile. This
       feature completely eliminates the need for this kind of rule in
       Rust.
   * - `FIO39 <https://wiki.sei.cmu.edu/confluence/display/c/FIO39-C.+Do+not+alternately+input+and+output+from+a+stream+without+an+intervening+flush+or+positioning+call>`__
     - Do not alternately input and output from a stream without an
       intervening flush or positioning call
     - 
     - 
     - This is UB in C, due to implementation details of the stream
       handling APIs. The implementation of those APIs in Rust is
       different, so the guideline doesn’t really map to it. \ *For more
       information, see* `this
       comment <https://github.com/Safety-Critical-Rust-Consortium/safety-critical-rust-coding-guidelines/issues/336#issuecomment-3764046307>`__
       *and* `this
       issue <https://github.com/Safety-Critical-Rust-Consortium/safety-critical-rust-coding-guidelines/issues/392>`__\ *.*
   * - `FIO44 <https://wiki.sei.cmu.edu/confluence/display/c/FIO44-C.+Only+use+values+for+fsetpos%28%29+that+are+returned+from+fgetpos%28%29>`__
     - Only use values for fsetpos() that are returned from fgetpos()
     - 
     - 
     - The closest APIs in Rust’s ``std`` to C’s ``fsetpos`` and
       ``fgetpos`` are the ones provided by the
       ```std::io::Seek`` <https://doc.rust-lang.org/std/io/trait.Seek.html>`__
       trait. Their main differences can be summarized by two things:-
       The foundational method of the trait,
       ```Seek::seek`` <https://doc.rust-lang.org/std/io/trait.Seek.html#tymethod.seek>`__,
       seeks by the number of bytes given to it. It doesn’t require the
       “multibyte parser state” that’s sometimes encoded in the
       ``fpos_t`` parameter for ``fsetpos``, since the trait has no
       notion of wide-oriented streams.- There is no Undefined Behavior
       in ``Seek``\ ’s APIs.Thus, there is no reason to restrict the
       provenance of the offsets used there.
   * - `ERR33 <https://wiki.sei.cmu.edu/confluence/display/c/ERR33-C.+Detect+and+handle+standard+library+errors>`__
     - Detect and handle standard library errors
     - 
     - 
     - Functions in std that may fail, wrap their result in the
       ``Result<T, E>`` type, which forces the caller to handle the
       error case whenever it happens. Thus, this rule is already
       enforced by the compiler.
   * - `MSC37 <https://wiki.sei.cmu.edu/confluence/display/c/MSC37-C.+Ensure+that+control+never+reaches+the+end+of+a+non-void+function>`__
     - Ensure that control never reaches the end of a non-void function
     - 
     - 
     - *Rationale: this is already enforced by the type system*
   * - `PRE32 <https://wiki.sei.cmu.edu/confluence/display/c/PRE32-C.+Do+not+use+preprocessor+directives+in+invocations+of+function-like+macros>`__
     - Do not use preprocessor directives in invocations of
       function-like macros
     - 
     - 
     - This rule is needed in C due to how its preprocessor works. It’s
       very C-preprocessor-specific, and doesn’t map to Rust
   * - `DCL31 <https://wiki.sei.cmu.edu/confluence/display/c/DCL31-C.+Declare+identifiers+before+using+them>`__
     - Declare identifiers before using them
     - 
     - 
     - Inferred types in Rust must always type-check. Not doing so
       results in a compile-time error. Therefore, the use case for this
       rule doesn’t exist in Rust.
   * - `DCL37 <https://wiki.sei.cmu.edu/confluence/display/c/DCL37-C.+Do+not+declare+or+define+a+reserved+identifier>`__
     - Do not declare or define a reserved identifier
     - 
     - 
     - **Context** *In C, reserved identifiers include more than just
       keywords. They include library functions and variables (eg
       ``memcpy``, ``errno``)), including some well-known ones (eg
       ``abs``). C also lists many identifiers as potentially reserved
       (eg anything beginning with ``str``). It is possible to redefine
       (and thus override) such global identifiers in C, such as by
       adding* ``#define errno my_errno`` *to a header, which would
       break most C programs.*\ Rust’s scoping rules already prevent
       this kind of breakage. Any form of behavior override is locally
       scoped, and explicitly opted into by the affected parts.
   * - `EXP37 <https://wiki.sei.cmu.edu/confluence/display/c/EXP37-C.+Call+functions+with+the+correct+number+and+type+of+arguments>`__
     - Call functions with the correct number and type of arguments
     - 
     - 
     - This is enforced by the type system
   * - `EXP44 <https://wiki.sei.cmu.edu/confluence/display/c/EXP44-C.+Do+not+rely+on+side+effects+in+operands+to+sizeof%2C+_Alignof%2C+or+_Generic>`__
     - Do not rely on side effects in operands to sizeof, \_Alignof or
       \_Generic
     - 
     - 
     - This is C-specific
   * - `EXP47 <https://wiki.sei.cmu.edu/confluence/display/c/EXP47-C.+Do+not+call+va_arg+with+an+argument+of+the+incorrect+type>`__
     - Do not call va_arg with an argument of the incorrect type
     - 
     - 
     - Variadic Functions don’t exist in Safe Rust. They do exist in
       **Unsafe Rust**, in the form of C’s Variadic Functions. These
       exist as a way to declare and implement variadic functions for
       FFI contexts.That being said, this rule doesn’t map to Rust,
       because while `it is possible to implement C variadic functions
       incorrectly <https://doc.rust-lang.org/std/ffi/struct.VaList.html#safety>`__,
       that issue is covered by the more general rule of `Callers of any
       unsafe fn shall abide by the function’s Safety
       contract <https://github.com/Safety-Critical-Rust-Consortium/safety-critical-rust-coding-guidelines/issues/337>`__.\ *Addendum:
       it is very reasonable to argue for a rule along the lines of
       “C-variadic functions should not be used outside of FFI
       contexts”, but such a rule would not be a mapping of CERT-C’s
       EXP47 rule. That is left for future work.*
   * - `STR34 <https://wiki.sei.cmu.edu/confluence/display/c/STR34-C.+Cast+characters+to+unsigned+char+before+converting+to+larger+integer+sizes>`__
     - Cast characters to unsigned char before converting to larger
       integer sizes
     - 
     - 
     - Characters in Rust are not integers.They are `unicode scalar
       values <https://www.unicode.org/glossary/#unicode_scalar_value>`__.
   * - `FIO30 <https://wiki.sei.cmu.edu/confluence/display/c/FIO30-C.+Exclude+user+input+from+format+strings>`__
     - Exclude user input from format strings
     - 
     - 
     - Format strings are evaluated at compile time in Rust
   * - `FIO41 <https://wiki.sei.cmu.edu/confluence/display/c/FIO41-C.+Do+not+call+getc%28%29%2C+putc%28%29%2C+getwc%28%29%2C+or+putwc%28%29+with+a+stream+argument+that+has+side+effects>`__
     - Do not call getc(), putc(), getwc() or putwc() with a stream
       argument that has side effects
     - 
     - 
     - This rule arises from how those APIs are implemented (as C
       macros), and not from a more general aspect of the situation.
   * - `ENV30 <https://wiki.sei.cmu.edu/confluence/display/c/ENV30-C.+Do+not+modify+the+object+referenced+by+the+return+value+of+certain+functions>`__
     - Do not modify the object referenced by the return value of
       certain functions
     - 
     - 
     - Immutability, when required, is always enforced in Rust.\ *I
       believe that Unsafe Rust could get away with doing this, jumping
       through some hoops. But that would lie in the vecinity of “Do not
       modify values whose validity invariant requires them to be
       immutable”. Breaking validity invariants is, of course, UB.*
   * - `ENV32 <https://wiki.sei.cmu.edu/confluence/display/c/ENV32-C.+All+exit+handlers+must+return+normally>`__
     - All exit handlers must return normally
     - 
     - 
     - Panicking doesn’t have UB. Panics inside of panics will
       eventually abort the program.
   * - `ERR34 <https://wiki.sei.cmu.edu/confluence/display/c/ERR34-C.+Detect+errors+when+converting+a+string+to+a+number>`__
     - Detect errors when converting a string to a number
     - 
     - 
     - Functions in std that may fail, wrap their result in the
       ``Result<T, E>`` type, which forces the caller to handle the
       error case whenever it happens. Thus, this rule is already
       enforced by the compiler.
   * - `DCL36 <https://wiki.sei.cmu.edu/confluence/display/c/DCL36-C.+Do+not+declare+an+identifier+with+conflicting+linkage+classifications>`__
     - Do not declare an identifier with conflicting linkage
       classifications
     - 
     - 
     - This is a very specific issue to C
   * - `DCL41 <https://wiki.sei.cmu.edu/confluence/display/c/DCL41-C.+Do+not+declare+variables+inside+a+switch+statement+before+the+first+case+label>`__
     - Do not declare variables inside a switch statement before the
       first case label
     - 
     - 
     - The semantics of C’s ``switch`` statements are (fortunately) not
       present in Rust
   * - `EXP45 <https://wiki.sei.cmu.edu/confluence/display/c/EXP45-C.+Do+not+perform+assignments+in+selection+statements>`__
     - Do not perform assignments in selection statements
     - 
     - 
     - Rust is expression-oriented. Assignments return ``()`` in Rust.
       Therefore the use-case for this is not really present in Rust.
   * - `EXP46 <https://wiki.sei.cmu.edu/confluence/display/c/EXP46-C.+Do+not+use+a+bitwise+operator+with+a+Boolean-like+operand>`__
     - Do not use a bitwise operator with a Boolean-like operand
     - 
     - 
     - The type system makes usage of these operators a reasonable thing
       in Rust. They are well-defined and well-behaved.
   * - `FIO38 <https://wiki.sei.cmu.edu/confluence/display/c/FIO38-C.+Do+not+copy+a+FILE+object>`__
     - Do not copy a FILE object
     - 
     - 
     - This is related to how the ``FILE`` object has
       implementation-defined behavior. This is completely C-specific,
       in this case.
   * - `FIO40 <https://wiki.sei.cmu.edu/confluence/display/c/FIO40-C.+Reset+strings+on+fgets%28%29++or+fgetws%28%29+failure>`__
     - Reset strings on fgets() or fgetws() failure
     - 
     - 
     - Unlike in the original ``fgets()`` and ``fgetws()``
       implementation, the bytes of the buffer ``buf`` in the
       io-reading-APIs of Rust’s ``std`` have very well-defined values
       in all scenarios: they follow the rules of the ``Read`` trait and
       its
       ```read`` <https://doc.rust-lang.org/std/io/trait.Read.html#tymethod.read>`__
       function. From those building blocks is that functions such as
       ```Read::read_to_string`` <https://doc.rust-lang.org/std/io/trait.Read.html#method.read_to_string>`__
       are constructed.As the root cause of this problem isn’t present
       in Rust, this rule is not needed.
   * - `SIG30 <https://wiki.sei.cmu.edu/confluence/display/c/SIG30-C.+Call+only+asynchronous-safe+functions+within+signal+handlers>`__
     - Call only asynchronous-safe functions within signal handlers
     - 
     - 
     - Rust doesn’t provide support for signal handling in ``std``.
       Details as to why can be seen
       `here <https://github.com/rust-lang/rfcs/issues/1368>`__.Since
       this feature is not supported in Rust, the rule doesn’t
       apply.\ *That being said, there are crates which provide signal
       handling utilities. Some are mentioned in the linked thread
       above. Dear reader, use those crates at your own discretion.*
   * - `SIG31 <https://wiki.sei.cmu.edu/confluence/display/c/SIG31-C.+Do+not+access+shared+objects+in+signal+handlers>`__
     - Do not access shared objects in signal handlers
     - 
     - 
     - *Same as SIG30*
   * - `ERR30 <https://wiki.sei.cmu.edu/confluence/display/c/ERR30-C.+Take+care+when+reading+errno>`__
     - Take care when reading errno
     - 
     - 
     - Errno doesn’t exist in Rust.But furthermore, functions that may
       fail wrap their result in the ``Result<T, E>`` type, which forces
       the caller to handle the error case if and only if it happened.
   * - `ERR32 <https://wiki.sei.cmu.edu/confluence/display/c/ERR32-C.+Do+not+rely+on+indeterminate+values+of+errno>`__
     - Do not rely on indeterminate values of errno
     - 
     - 
     - *Rationale: see ERR30-C*
   * - `CON30 <https://wiki.sei.cmu.edu/confluence/display/c/CON30-C.+Clean+up+thread-specific+storage>`__
     - Clean up thread-specific storage
     - 
     - 
     - Thread-specific storage in Rust refers to values behind a
       ```LocalKey`` <https://doc.rust-lang.org/std/thread/struct.LocalKey.html>`__.There
       is no important difference between how this kind of storage is
       cleaned up and how other resources local to the thread (like its
       stack variables) are cleaned up. Thus, it does not merit its own
       rule.
   * - `CON39 <https://wiki.sei.cmu.edu/confluence/display/c/CON39-C.+Do+not+join+or+detach+a+thread+that+was+previously+joined+or+detached>`__
     - Do not join or detach a thread that was previously joined or
       detached
     - 
     - 
     - This does not apply to Rust because:-
       ```std::thread::JoinHandle::join`` <https://doc.rust-lang.org/std/thread/struct.JoinHandle.html#method.join>`__
       consumes the thread, and-
       ```JoinHandle`` <https://doc.rust-lang.org/std/thread/struct.JoinHandle.html>`__
       doesn’t implement ``Clone``, so it’s impossible to join it
       twice.Unsafe code would be needed to invalidly copy it. But then
       again, “Obey ownership semantics” can just be one rule.
   * - `INT35 <https://wiki.sei.cmu.edu/confluence/display/c/INT35-C.+Use+correct+integer+precisions>`__
     - Use correct integer precisions
     - 
     - 
     - All primitive integer types guarantee their precision in Rust
   * - `STR37 <https://wiki.sei.cmu.edu/confluence/display/c/STR37-C.+Arguments+to+character-handling+functions+must+be+representable+as+an+unsigned+char>`__
     - Arguments to character-handling functions must be representable
       as an unsigned char
     - 
     - 
     - Characters in Rust are not integers
   * - `STR38 <https://wiki.sei.cmu.edu/confluence/display/c/STR38-C.+Do+not+confuse+narrow+and+wide+character+strings+and+functions>`__
     - Do not confuse narrow and wide character strings and functions
     - 
     - 
     - There’s only one character type in Rust
   * - `MEM33 <https://wiki.sei.cmu.edu/confluence/display/c/MEM33-C.++Allocate+and+copy+structures+containing+a+flexible+array+member+dynamically>`__
     - Allocate and copy structures containing a flexible array member
       dynamically
     - 
     - 
     - Flexible array members are not a thing in Rust
   * - `FIO47 <https://wiki.sei.cmu.edu/confluence/display/c/FIO47-C.+Use+valid+format+strings>`__
     - Use valid format strings
     - 
     - 
     - Format strings are evaluated, and therefore, validated, at
       compile time, in Rust
   * - `SIG34 <https://wiki.sei.cmu.edu/confluence/display/c/SIG34-C.+Do+not+call+signal%28%29+from+within+interruptible+signal+handlers>`__
     - Do not call signal() from within interruptible signal handlers
     - 
     - 
     - Rust doesn’t provide support for signal handling in ``std``.
       Details as to why can be seen
       `here <https://github.com/rust-lang/rfcs/issues/1368>`__.Since
       this feature is not supported in Rust, the rule doesn’t
       apply.\ *That being said, there are crates which provide signal
       handling utilities. Some are mentioned in the linked thread
       above. Dear reader, use those crates at your own discretion.*
   * - `SIG35 <https://wiki.sei.cmu.edu/confluence/display/c/SIG35-C.+Do+not+return+from+a+computational+exception+signal+handler>`__
     - Do not return from a computational exception signal handler
     - 
     - 
     - *Rationale: see SIG34*
   * - `CON31 <https://wiki.sei.cmu.edu/confluence/display/c/CON31-C.+Do+not+destroy+a+mutex+while+it+is+locked>`__
     - Do not destroy a mutex while it is locked
     - 
     - 
     - This is impossible to do in Rust due to ownership semantics: it’s
       only possible to destroy things one has ``&mut`` access to.The
       user could use ``unsafe`` to invalidly create such a reference,
       but doing so would violate ownership semantics (and be immediate
       Undefined Behavior).
   * - `MSC33 <https://wiki.sei.cmu.edu/confluence/display/c/MSC33-C.+Do+not+pass+invalid+data+to+the+asctime%28%29+function>`__
     - Do not pass invalid data to the asctime() function
     - 
     - 
     - There is no equivalent time-displaying function in either
       ``core`` nor ``std``.\ *As of the time of writing (2026-03-03),
       this kind of functionality can be accessed through external
       libraries such as ``chrono``, ``hifitime``, ``icu``, ``jiff`` and
       ``time``.*
   * - `MSC38 <https://wiki.sei.cmu.edu/confluence/display/c/MSC38-C.+Do+not+treat+a+predefined+identifier+as+an+object+if+it+might+only+be+implemented+as+a+macro>`__
     - Do not treat a predefined identifier as an object if it might
       only be implemented as a macro
     - 
     - 
     - There is no such thing as a macro pointer in Rust
   * - `MSC39 <https://wiki.sei.cmu.edu/confluence/display/c/MSC39-C.+Do+not+call+va_arg%28%29+on+a+va_list+that+has+an+indeterminate+value>`__
     - Do not call va_arg() on a va_list that has an indeterminate value
     - 
     - 
     - Variadic functions do not exist in Rust
   * - `MSC40 <https://wiki.sei.cmu.edu/confluence/display/c/MSC40-C.+Do+not+violate+constraints>`__
     - Do not violate constraints
     - 
     - 
     - *Context of MSC40: this rule is about not writing code that
       doesn’t comply with the C standard.*\ The Rust compiler rejects
       all such programs. If a program is not valid Rust code, then it
       does not compile.
