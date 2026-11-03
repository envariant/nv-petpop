import type { components } from './schema';

type S = components['schemas'];
export type PetSpec = S['PetSpec'];
export type PetSpecPatch = Record<string, unknown>;
export type Species = S['PetSpec_species'];
export type Breed = S['Breed'];
export type BreedList = S['BreedList'];
export type Session = S['Session'];
export type ParseResponse = S['ParseResponse'];
export type Job = S['Job'];
export type JobCreated = S['JobCreated'];
export type JobStatus = Job['status'];
export type Stage = Job['stage'];
export type Artefact = S['Artefact'];
export type ProgressEvent = S['ProgressEvent'];
export type FulfilResponse = S['FulfilResponse'];
export type ResultPage = S['ResultPage'];
export type StaffQueue = S['StaffQueue'];
export type StaffJob = S['StaffJob'];
export type Health = S['Health'];
export type BespokeAccepted = S['BespokeAccepted'];
export type KioskOps = S['KioskOps'];
export type StaffToken = S['StaffToken'];
export type StaffUser = S['StaffUser'];
export type Role = StaffUser['role'];
// Library mode (BRIEF Section 16): Contract 1 (the release) and Contract 2 (the composition).
export type CompositionBody = S['Composition'];
export type ReleaseManifestBody = S['ReleaseManifest'];
export type LibraryRelease = S['LibraryRelease'];
export type LibraryFamilies = S['LibraryFamilies'];
export type LibraryParts = S['LibraryParts'];
export type LibraryPatterns = S['LibraryPatterns'];
export type CompositionStatus = S['CompositionStatus'];
export type CompositionState = CompositionStatus['status'];
export type ExportAccepted = S['ExportAccepted'];
export type KioskOrder = S['KioskOrder'];
// Payment for an order (decision 125).
export type Payment = S['Payment'];
export type PaymentMethod = Payment['method'];
export type PaymentOffer = S['PaymentOffer'];
export type Price = S['Price'];
export type Quote = S['Quote'];
// Customer accounts (decision 126).
export type Account = S['Account'];
export type AccountSession = S['AccountSession'];
export type AuthConfig = S['AuthConfig'];
export type CodeSent = S['CodeSent'];
export type Channel = S['CodeRequest']['channel'];
export type Provider = Account['providers'][number];
export type OrderContact = S['OrderContact'];
export type AccountOrders = S['AccountOrders'];
// The part library (decision 127).
export type Part = S['Part'];
export type PartKit = S['PartKit'];
export type PartKitSummary = S['PartKitSummary'];
export type PartKitList = S['PartKitList'];
export type PartUploadResult = S['PartUploadResult'];
export type PartRigPatch = S['PartRigPatch'];
export type PartKitSetup = S['PartKitSetup'];
export type Pose = S['Pose'];
// Studio curation (M8).
export type BatchCreate = S['BatchCreate'];
export type Batch = S['Batch'];
export type BatchList = S['BatchList'];
export type BatchFigurine = S['BatchFigurine'];
export type LibraryCandidate = S['LibraryCandidate'];
export type ReviewDecision = S['ReviewDecision'];
export type LibraryItem = S['LibraryItem'];
export type LibraryItemList = S['LibraryItemList'];
export type LibraryItemPatch = S['LibraryItemPatch'];
export type ItemKind = LibraryItem['kind'];
export type ItemStatus = LibraryItem['status'];
export type ReleaseInfo = S['ReleaseInfo'];
export type ReleaseList = S['ReleaseList'];
// Manual mode (decision 111, API 3.2.0): provider requests the operator runs in the vendor's app.
export type ManualTask = S['ManualTask'];
export type ManualTaskList = S['ManualTaskList'];
export type ManualInput = S['ManualInput'];
export type ManualCapability = ManualTask['capability'];
// Per-job GenAI profiles (decision 113, API 3.3.0).
export type GenaiProfiles = S['GenaiProfiles'];
export type GenaiProfileInfo = S['GenaiProfileInfo'];
export type GenaiPipeline = S['GenaiPipeline'];
export type GenaiOption = S['GenaiOption'];
