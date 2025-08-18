/**
 * Deklarasi minimal agar tree-shakable:
 *  • filterFieldProps, makeVFieldProps, VField
 *  • makeVInputProps, VInput.filterProps
 *  • filterInputAttrs
 */

declare module 'vuetify/lib/components/VField/VField' {
  export const filterFieldProps: (props: any) => any
  export const makeVFieldProps: (opts?: any) => any
  export const VField: any
}

declare module 'vuetify/lib/components/VInput/VInput' {
  export const makeVInputProps: (opts?: any) => any
  export const VInput: {
    filterProps: (props: any) => any
  }
}

declare module 'vuetify/lib/util/helpers' {
  export const filterInputAttrs: (
    attrs: Record<string, any>,
  ) => [Record<string, any>, Record<string, any>]
}
