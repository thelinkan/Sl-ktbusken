# Description

Build a geneology program, with Swedish context as main point of the project. The main program should be written in python with Pyside6. In addition, when the main program is done, I would like to make a webb app that is read only and can present the things in the tree in logged in mode only

## Datamodel (json)

The main file for the tree, the sources, places etc should be palced in a gzipped json file. In addition there need to be special files for translation of imported gedcom files from other programs. For example the places and sources will have a more elaborate way to be stored in the app-json than in gedcom. There also needs to be created on first import a special file for translation of individuals and relationsships from gedcom to json format, so that if the gedcom-file is updated, the import funktion can be used to updated the json, rather than creating it from scratch.

The app-json should have a format inspired by, but not limited to this example:

{
  "format": "släktbuske-file",
  "version": "0.1",
  "project": {
    "title": "Exempelsläkt",
    "main_person_id": "person_001",
    "created_by": "Släktbuske",
    "language": "sv-SE"
  },

  "persons": [
    {
      "id": "person_001",
      "sex": "M",
      "names": [
        {
          "type": "birth",
          "given": "Erik Johan",
          "surname": "Lindström"
        }
      ],
      "profile_media_id": "media_photo_001",
      "notes": "Huvudperson."
    },
    {
      "id": "person_002",
      "sex": "F",
      "names": [
        {
          "type": "birth",
          "given": "Anna Maria",
          "surname": "Sjöberg"
        }
      ],
      "notes": "Huvudpersonens maka."
    },
    {
      "id": "person_003",
      "sex": "F",
      "names": [
        {
          "type": "birth",
          "given": "Karin Elisabeth",
          "surname": "Lindström"
        }
      ]
    },
    {
      "id": "person_004",
      "sex": "M",
      "names": [
        {
          "type": "birth",
          "given": "Lars Erik",
          "surname": "Lindström"
        }
      ]
    },

    {
      "id": "person_005",
      "sex": "M",
      "names": [
        {
          "type": "birth",
          "given": "Karl August",
          "surname": "Lindström"
        }
      ],
      "notes": "Huvudpersonens far."
    },
    {
      "id": "person_006",
      "sex": "F",
      "names": [
        {
          "type": "birth",
          "given": "Brita Kristina",
          "surname": "Andersdotter"
        }
      ],
      "notes": "Huvudpersonens mor."
    },

    {
      "id": "person_007",
      "sex": "M",
      "names": [
        {
          "type": "birth",
          "given": "Johan Petter",
          "surname": "Lindström"
        }
      ],
      "notes": "Farfar."
    },
    {
      "id": "person_008",
      "sex": "F",
      "names": [
        {
          "type": "birth",
          "given": "Märta Sofia",
          "surname": "Persdotter"
        }
      ],
      "notes": "Farmor."
    },
    {
      "id": "person_009",
      "sex": "M",
      "names": [
        {
          "type": "birth",
          "given": "Anders Olof",
          "surname": "Nilsson"
        }
      ],
      "notes": "Morfar."
    },
    {
      "id": "person_010",
      "sex": "F",
      "names": [
        {
          "type": "birth",
          "given": "Stina Kajsa",
          "surname": "Larsdotter"
        }
      ],
      "notes": "Mormor."
    },

    {
      "id": "person_011",
      "sex": "F",
      "names": [
        {
          "type": "birth",
          "given": "Eva Kristina",
          "surname": "Lindström"
        }
      ],
      "notes": "Huvudpersonens syster."
    },
    {
      "id": "person_012",
      "sex": "M",
      "names": [
        {
          "type": "birth",
          "given": "Nils Gunnar",
          "surname": "Berg"
        }
      ],
      "notes": "Systerns make."
    },
    {
      "id": "person_013",
      "sex": "F",
      "names": [
        {
          "type": "birth",
          "given": "Sara Helena",
          "surname": "Berg"
        }
      ],
      "notes": "Huvudpersonens systerdotter."
    }
  ],

  "families": [
    {
      "id": "family_001",
      "partners": [
        {
          "person_id": "person_001",
          "role": "husband"
        },
        {
          "person_id": "person_002",
          "role": "wife"
        }
      ],
      "children": [
        "person_003",
        "person_004"
      ],
      "event_ids": [
        "event_marriage_001"
      ]
    },
    {
      "id": "family_002",
      "partners": [
        {
          "person_id": "person_005",
          "role": "father"
        },
        {
          "person_id": "person_006",
          "role": "mother"
        }
      ],
      "children": [
        "person_001",
        "person_011"
      ],
      "event_ids": [
        "event_marriage_002"
      ]
    },
    {
      "id": "family_003",
      "partners": [
        {
          "person_id": "person_007",
          "role": "father"
        },
        {
          "person_id": "person_008",
          "role": "mother"
        }
      ],
      "children": [
        "person_005"
      ],
      "event_ids": [
        "event_marriage_003"
      ]
    },
    {
      "id": "family_004",
      "partners": [
        {
          "person_id": "person_009",
          "role": "father"
        },
        {
          "person_id": "person_010",
          "role": "mother"
        }
      ],
      "children": [
        "person_006"
      ],
      "event_ids": [
        "event_marriage_004"
      ]
    },
    {
      "id": "family_005",
      "partners": [
        {
          "person_id": "person_011",
          "role": "wife"
        },
        {
          "person_id": "person_012",
          "role": "husband"
        }
      ],
      "children": [
        "person_013"
      ],
      "event_ids": [
        "event_marriage_005"
      ]
    }
  ],

  "events": [
    {
      "id": "event_birth_001",
      "type": "birth",
      "participants": [
        {
          "person_id": "person_001",
          "role": "child"
        }
      ],
      "date": {
        "value": "1970-06-15",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_svb_1970_001",
            "quality": "secondary",
            "note": "Födelsedatum enligt Sveriges Befolkning 1970."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_parish",
        "source_refs": [
          {
            "source_id": "source_svb_1970_001",
            "quality": "secondary",
            "note": "Födelseförsamling enligt Sveriges Befolkning 1970."
          }
        ]
      }
    },
    {
      "id": "event_marriage_001",
      "type": "marriage",
      "participants": [
        {
          "person_id": "person_001",
          "role": "spouse"
        },
        {
          "person_id": "person_002",
          "role": "spouse"
        }
      ],
      "date": {
        "value": "1995-08-12",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_marriage_001",
            "quality": "primary",
            "note": "Vigselbok."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_church",
        "source_refs": [
          {
            "source_id": "source_marriage_001",
            "quality": "primary",
            "note": "Vigselplats enligt vigselboken."
          }
        ]
      }
    },
    {
      "id": "event_birth_003",
      "type": "birth",
      "participants": [
        {
          "person_id": "person_003",
          "role": "child"
        }
      ],
      "date": {
        "value": "1998-03-04",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_birth_003",
            "quality": "primary",
            "note": "Födelsebok."
          }
        ]
      },
      "place": {
        "place_id": "place_hudiksvall_parish",
        "source_refs": [
          {
            "source_id": "source_birth_003",
            "quality": "primary",
            "note": "Födelseförsamling."
          }
        ]
      }
    },
    {
      "id": "event_birth_004",
      "type": "birth",
      "participants": [
        {
          "person_id": "person_004",
          "role": "child"
        }
      ],
      "date": {
        "value": "2001-11-22",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_birth_004",
            "quality": "primary",
            "note": "Födelsebok."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_parish",
        "source_refs": [
          {
            "source_id": "source_birth_004",
            "quality": "primary",
            "note": "Födelseförsamling."
          }
        ]
      }
    },

    {
      "id": "event_birth_005",
      "type": "birth",
      "participants": [
        {
          "person_id": "person_005",
          "role": "child"
        }
      ],
      "date": {
        "value": "1944-02-19",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_birth_005",
            "quality": "primary",
            "note": "Födelsebok."
          }
        ]
      },
      "place": {
        "place_id": "place_farila_parish",
        "source_refs": [
          {
            "source_id": "source_birth_005",
            "quality": "primary",
            "note": "Födelseförsamling."
          }
        ]
      }
    },
    {
      "id": "event_birth_006",
      "type": "birth",
      "participants": [
        {
          "person_id": "person_006",
          "role": "child"
        }
      ],
      "date": {
        "value": "1947-09-03",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_birth_006",
            "quality": "primary",
            "note": "Födelsebok."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_parish",
        "source_refs": [
          {
            "source_id": "source_birth_006",
            "quality": "primary",
            "note": "Födelseförsamling."
          }
        ]
      }
    },
    {
      "id": "event_marriage_002",
      "type": "marriage",
      "participants": [
        {
          "person_id": "person_005",
          "role": "spouse"
        },
        {
          "person_id": "person_006",
          "role": "spouse"
        }
      ],
      "date": {
        "value": "1968-05-18",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_marriage_002",
            "quality": "primary",
            "note": "Vigselbok."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_church",
        "source_refs": [
          {
            "source_id": "source_marriage_002",
            "quality": "primary",
            "note": "Vigselplats."
          }
        ]
      }
    },
    {
      "id": "event_death_005",
      "type": "death",
      "participants": [
        {
          "person_id": "person_005",
          "role": "deceased"
        }
      ],
      "date": {
        "value": "2018-10-14",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_death_notice_005",
            "quality": "secondary",
            "note": "Datum enligt dödsannons."
          },
          {
            "source_id": "source_sdb_005",
            "quality": "secondary",
            "note": "Datum enligt Sveriges dödbok."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_parish",
        "source_refs": [
          {
            "source_id": "source_sdb_005",
            "quality": "secondary",
            "note": "Dödsförsamling enligt Sveriges dödbok."
          }
        ]
      },
      "media_ids": [
        "media_death_notice_005"
      ]
    },
    {
      "id": "event_burial_005",
      "type": "burial",
      "participants": [
        {
          "person_id": "person_005",
          "role": "deceased"
        }
      ],
      "date": {
        "value": "2018-11-02",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_death_notice_005",
            "quality": "secondary",
            "note": "Begravningsdatum enligt dödsannons."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_cemetery",
        "source_refs": [
          {
            "source_id": "source_death_notice_005",
            "quality": "secondary",
            "note": "Begravningsplats enligt dödsannons."
          }
        ]
      },
      "media_ids": [
        "media_death_notice_005",
        "media_grave_005"
      ]
    },

    {
      "id": "event_birth_011",
      "type": "birth",
      "participants": [
        {
          "person_id": "person_011",
          "role": "child"
        }
      ],
      "date": {
        "value": "1973-04-21",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_svb_1980_011",
            "quality": "secondary",
            "note": "Födelsedatum enligt Sveriges Befolkning 1980."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_parish",
        "source_refs": [
          {
            "source_id": "source_svb_1980_011",
            "quality": "secondary",
            "note": "Födelseförsamling enligt Sveriges Befolkning 1980."
          }
        ]
      }
    },
    {
      "id": "event_marriage_005",
      "type": "marriage",
      "participants": [
        {
          "person_id": "person_011",
          "role": "spouse"
        },
        {
          "person_id": "person_012",
          "role": "spouse"
        }
      ],
      "date": {
        "value": "1997-06-07",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_marriage_005",
            "quality": "primary",
            "note": "Vigselbok."
          }
        ]
      },
      "place": {
        "place_id": "place_ljusdal_church",
        "source_refs": [
          {
            "source_id": "source_marriage_005",
            "quality": "primary",
            "note": "Vigselplats."
          }
        ]
      }
    },
    {
      "id": "event_birth_013",
      "type": "birth",
      "participants": [
        {
          "person_id": "person_013",
          "role": "child"
        }
      ],
      "date": {
        "value": "2002-02-10",
        "precision": "day",
        "source_refs": [
          {
            "source_id": "source_birth_013",
            "quality": "primary",
            "note": "Födelsebok."
          }
        ]
      },
      "place": {
        "place_id": "place_hudiksvall_parish",
        "source_refs": [
          {
            "source_id": "source_birth_013",
            "quality": "primary",
            "note": "Födelseförsamling."
          }
        ]
      }
    }
  ],

  "places": [
    {
      "id": "place_sweden",
      "type": "country",
      "name": "Sverige"
    },
    {
      "id": "place_gavleborg_county",
      "type": "county",
      "name": "Gävleborgs län",
      "parent_place_id": "place_sweden"
    },
    {
      "id": "place_stockholm_county",
      "type": "county",
      "name": "Stockholms län",
      "parent_place_id": "place_sweden"
    },
    {
      "id": "place_ljusdal_parish",
      "type": "parish",
      "name": "Ljusdal",
      "parent_place_id": "place_gavleborg_county",
      "country": "Sverige",
      "county": "Gävleborgs län",
      "latitude": 61.828,
      "longitude": 16.091,
      "notes": "Socken/församling i Hälsingland."
    },
    {
      "id": "place_farila_parish",
      "type": "parish",
      "name": "Färila",
      "parent_place_id": "place_gavleborg_county",
      "country": "Sverige",
      "county": "Gävleborgs län",
      "latitude": 61.800,
      "longitude": 15.850,
      "notes": ""
    },
    {
      "id": "place_hudiksvall_parish",
      "type": "parish",
      "name": "Hudiksvall",
      "parent_place_id": "place_gavleborg_county",
      "country": "Sverige",
      "county": "Gävleborgs län",
      "latitude": 61.728,
      "longitude": 17.105,
      "notes": ""
    },
    {
      "id": "place_ljusdal_church",
      "type": "church",
      "name": "Ljusdals kyrka",
      "parent_place_id": "place_ljusdal_parish",
      "parish_id": "place_ljusdal_parish",
      "country": "Sverige",
      "county": "Gävleborgs län",
      "latitude": 61.827,
      "longitude": 16.096,
      "notes": "Specifik plats inom Ljusdals socken."
    },
    {
      "id": "place_ljusdal_cemetery",
      "type": "cemetery",
      "name": "Ljusdals kyrkogård",
      "parent_place_id": "place_ljusdal_parish",
      "parish_id": "place_ljusdal_parish",
      "country": "Sverige",
      "county": "Gävleborgs län",
      "latitude": 61.827,
      "longitude": 16.097,
      "notes": ""
    },
    {
      "id": "place_brannkyrka_parish",
      "type": "parish",
      "name": "Brännkyrka",
      "parent_place_id": "place_stockholm_county",
      "country": "Sverige",
      "county": "Stockholms län",
      "historical_county_code": "AB",
      "latitude": 59.285,
      "longitude": 18.000,
      "notes": ""
    }
  ],

  "sources": [
    {
      "id": "source_svb_1970_001",
      "provider": "Sveriges Befolkning 1970",
      "source_type": "database",
      "title": "Sveriges Befolkning 1970",
      "reference_text": "",
      "provider_ref": "",
      "short_note": "SvBef1970",
      "free_note": "Använd för huvudpersonens födelsedatum och födelseförsamling.",
      "structured_reference": {},
      "media_ids": []
    },
    {
      "id": "source_svb_1980_011",
      "provider": "Sveriges Befolkning 1980",
      "source_type": "database",
      "title": "Sveriges Befolkning 1980",
      "reference_text": "",
      "provider_ref": "",
      "short_note": "SvBef1980",
      "free_note": "Använd för systerns födelseuppgift.",
      "structured_reference": {},
      "media_ids": []
    },

    {
      "id": "source_birth_003",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Hudiksvall (X) C:12 (1995-2000)",
      "reference_text": "ArkivDigital: Hudiksvall (X) C:12 (1995-2000) Bild: 123",
      "provider_ref": "v900003.b123",
      "short_note": "Födelsebok",
      "free_note": "",
      "structured_reference": {
        "parish": "Hudiksvall",
        "county_code": "X",
        "series": "C",
        "volume": "12",
        "years": "1995-2000",
        "image": "123",
        "page": null
      },
      "media_ids": [
        "media_source_birth_003"
      ]
    },
    {
      "id": "source_birth_004",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Ljusdal (X) C:15 (2000-2005)",
      "reference_text": "ArkivDigital: Ljusdal (X) C:15 (2000-2005) Bild: 44",
      "provider_ref": "v900004.b44",
      "short_note": "Födelsebok",
      "free_note": "",
      "structured_reference": {
        "parish": "Ljusdal",
        "county_code": "X",
        "series": "C",
        "volume": "15",
        "years": "2000-2005",
        "image": "44",
        "page": null
      },
      "media_ids": []
    },
    {
      "id": "source_birth_005",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Färila (X) C:9 (1940-1946)",
      "reference_text": "ArkivDigital: Färila (X) C:9 (1940-1946) Bild: 87",
      "provider_ref": "v900005.b87",
      "short_note": "Födelsebok",
      "free_note": "",
      "structured_reference": {
        "parish": "Färila",
        "county_code": "X",
        "series": "C",
        "volume": "9",
        "years": "1940-1946",
        "image": "87",
        "page": null
      },
      "media_ids": []
    },
    {
      "id": "source_birth_006",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Ljusdal (X) C:10 (1945-1950)",
      "reference_text": "ArkivDigital: Ljusdal (X) C:10 (1945-1950) Bild: 61",
      "provider_ref": "v900006.b61",
      "short_note": "Födelsebok",
      "free_note": "",
      "structured_reference": {
        "parish": "Ljusdal",
        "county_code": "X",
        "series": "C",
        "volume": "10",
        "years": "1945-1950",
        "image": "61",
        "page": null
      },
      "media_ids": []
    },
    {
      "id": "source_birth_013",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Hudiksvall (X) C:13 (2000-2005)",
      "reference_text": "ArkivDigital: Hudiksvall (X) C:13 (2000-2005) Bild: 19",
      "provider_ref": "v900013.b19",
      "short_note": "Födelsebok",
      "free_note": "",
      "structured_reference": {
        "parish": "Hudiksvall",
        "county_code": "X",
        "series": "C",
        "volume": "13",
        "years": "2000-2005",
        "image": "19",
        "page": null
      },
      "media_ids": []
    },

    {
      "id": "source_marriage_001",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Ljusdal (X) EI:7 (1990-1999)",
      "reference_text": "ArkivDigital: Ljusdal (X) EI:7 (1990-1999) Bild: 102",
      "provider_ref": "v910001.b102",
      "short_note": "Vigselbok",
      "free_note": "",
      "structured_reference": {
        "parish": "Ljusdal",
        "county_code": "X",
        "series": "EI",
        "volume": "7",
        "years": "1990-1999",
        "image": "102",
        "page": null
      },
      "media_ids": []
    },
    {
      "id": "source_marriage_002",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Ljusdal (X) EI:5 (1960-1970)",
      "reference_text": "ArkivDigital: Ljusdal (X) EI:5 (1960-1970) Bild: 56",
      "provider_ref": "v910002.b56",
      "short_note": "Vigselbok",
      "free_note": "",
      "structured_reference": {
        "parish": "Ljusdal",
        "county_code": "X",
        "series": "EI",
        "volume": "5",
        "years": "1960-1970",
        "image": "56",
        "page": null
      },
      "media_ids": []
    },
    {
      "id": "source_marriage_003",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Färila (X) EI:3 (1920-1935)",
      "reference_text": "ArkivDigital: Färila (X) EI:3 (1920-1935) Bild: 33",
      "provider_ref": "v910003.b33",
      "short_note": "Vigselbok",
      "free_note": "",
      "structured_reference": {
        "parish": "Färila",
        "county_code": "X",
        "series": "EI",
        "volume": "3",
        "years": "1920-1935",
        "image": "33",
        "page": null
      },
      "media_ids": []
    },
    {
      "id": "source_marriage_004",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Ljusdal (X) EI:4 (1930-1945)",
      "reference_text": "ArkivDigital: Ljusdal (X) EI:4 (1930-1945) Bild: 75",
      "provider_ref": "v910004.b75",
      "short_note": "Vigselbok",
      "free_note": "",
      "structured_reference": {
        "parish": "Ljusdal",
        "county_code": "X",
        "series": "EI",
        "volume": "4",
        "years": "1930-1945",
        "image": "75",
        "page": null
      },
      "media_ids": []
    },
    {
      "id": "source_marriage_005",
      "provider": "ArkivDigital",
      "source_type": "church_book",
      "title": "Ljusdal (X) EI:8 (1995-2005)",
      "reference_text": "ArkivDigital: Ljusdal (X) EI:8 (1995-2005) Bild: 24",
      "provider_ref": "v910005.b24",
      "short_note": "Vigselbok",
      "free_note": "",
      "structured_reference": {
        "parish": "Ljusdal",
        "county_code": "X",
        "series": "EI",
        "volume": "8",
        "years": "1995-2005",
        "image": "24",
        "page": null
      },
      "media_ids": []
    },

    {
      "id": "source_death_notice_005",
      "provider": "Tidningsarkiv",
      "source_type": "death_notice",
      "title": "Dödsannons för Karl August Lindström",
      "reference_text": "Ljusdals-Posten, 2018-10-20",
      "provider_ref": "",
      "short_note": "Dödsannons",
      "free_note": "Anger dödsdatum och begravningsdatum.",
      "structured_reference": {
        "newspaper": "Ljusdals-Posten",
        "publication_date": "2018-10-20",
        "page": null
      },
      "media_ids": [
        "media_death_notice_005"
      ]
    },
    {
      "id": "source_sdb_005",
      "provider": "Sveriges dödbok",
      "source_type": "database",
      "title": "Sveriges dödbok",
      "reference_text": "",
      "provider_ref": "",
      "short_note": "SvDöd",
      "free_note": "Använd för dödsdatum och dödsförsamling.",
      "structured_reference": {},
      "media_ids": []
    }
  ],

  "media": [
    {
      "id": "media_photo_001",
      "type": "photo",
      "file": "media/photos/erik_johan_lindstrom.jpg",
      "title": "Profilfoto av Erik Johan Lindström",
      "linked_entities": [
        {
          "entity_type": "person",
          "entity_id": "person_001",
          "role": "portrait"
        }
      ]
    },
    {
      "id": "media_source_birth_003",
      "type": "source_image",
      "file": "media/sources/hudiksvall_c12_bild123.jpg",
      "title": "Födelsenotis för Karin Elisabeth Lindström",
      "linked_entities": [
        {
          "entity_type": "source",
          "entity_id": "source_birth_003",
          "role": "source_scan"
        },
        {
          "entity_type": "event",
          "entity_id": "event_birth_003",
          "role": "evidence"
        }
      ]
    },
    {
      "id": "media_death_notice_005",
      "type": "death_notice",
      "file": "media/death_notices/karl_august_lindstrom_2018.jpg",
      "title": "Dödsannons för Karl August Lindström",
      "publication": {
        "newspaper": "Ljusdals-Posten",
        "date": "2018-10-20",
        "page": null
      },
      "transcription": "Fiktiv avskrift av dödsannonsen.",
      "linked_entities": [
        {
          "entity_type": "person",
          "entity_id": "person_005",
          "role": "subject"
        },
        {
          "entity_type": "event",
          "entity_id": "event_death_005",
          "role": "evidence"
        },
        {
          "entity_type": "event",
          "entity_id": "event_burial_005",
          "role": "evidence"
        }
      ],
      "mentioned_person_ids": [
        "person_001",
        "person_006",
        "person_011"
      ]
    },
    {
      "id": "media_grave_005",
      "type": "grave_photo",
      "file": "media/graves/karl_august_lindstrom_grave.jpg",
      "title": "Gravsten för Karl August Lindström",
      "linked_entities": [
        {
          "entity_type": "person",
          "entity_id": "person_005",
          "role": "grave"
        },
        {
          "entity_type": "place",
          "entity_id": "place_ljusdal_cemetery",
          "role": "location"
        }
      ]
    },
    {
      "id": "media_logo_myheritage",
      "type": "logo",
      "file": "media/logos/myheritage.png",
      "title": "MyHeritage-logotyp"
    }
  ],

  "dna_companies": [
    {
      "id": "dna_company_myheritage",
      "name": "MyHeritage",
      "logo_media_id": "media_logo_myheritage",
      "description": "DNA-företag med autosomala matchningar och segmentdata."
    }
  ],

  "dna_profiles": [
    {
      "id": "dna_profile_001",
      "person_id": "person_001",
      "company_id": "dna_company_myheritage",
      "test_type": "autosomal",
      "kit_name": "Erik Johan Lindström",
      "kit_id": "",
      "admin_person_id": "person_001",
      "admin_status": "self",
      "notes": "Huvudpersonens DNA-test."
    },
    {
      "id": "dna_profile_005",
      "person_id": "person_005",
      "company_id": "dna_company_myheritage",
      "test_type": "autosomal",
      "kit_name": "Karl August Lindström",
      "kit_id": "",
      "admin_person_id": "person_001",
      "admin_status": "managed_by_user",
      "notes": "Faderns test administreras av huvudpersonen."
    },
    {
      "id": "dna_profile_006",
      "person_id": "person_006",
      "company_id": "dna_company_myheritage",
      "test_type": "autosomal",
      "kit_name": "Brita Kristina Andersdotter",
      "kit_id": "",
      "admin_person_id": "person_006",
      "admin_status": "self_managed",
      "notes": "Modern administrerar sitt eget test."
    },
    {
      "id": "dna_profile_013",
      "person_id": "person_013",
      "company_id": "dna_company_myheritage",
      "test_type": "autosomal",
      "kit_name": "Sara Helena Berg",
      "kit_id": "",
      "admin_person_id": "person_001",
      "admin_status": "managed_by_user",
      "notes": "Systerdotterns test administreras av huvudpersonen."
    }
  ],

  "dna_matches": [
    {
      "id": "dna_match_001_005",
      "profile1_id": "dna_profile_001",
      "profile2_id": "dna_profile_005",
      "company_id": "dna_company_myheritage",
      "shared_cm": 3485.2,
      "largest_segment_cm": 280.4,
      "segment_count": 28,
      "match_name_at_company": "Karl August Lindström",
      "company_match_id": "",
      "notes": "Förväntad far-son-match.",
      "source_refs": []
    },
    {
      "id": "dna_match_001_006",
      "profile1_id": "dna_profile_001",
      "profile2_id": "dna_profile_006",
      "company_id": "dna_company_myheritage",
      "shared_cm": 3502.8,
      "largest_segment_cm": 290.1,
      "segment_count": 29,
      "match_name_at_company": "Brita Kristina Andersdotter",
      "company_match_id": "",
      "notes": "Förväntad mor-son-match.",
      "source_refs": []
    },
    {
      "id": "dna_match_001_013",
      "profile1_id": "dna_profile_001",
      "profile2_id": "dna_profile_013",
      "company_id": "dna_company_myheritage",
      "shared_cm": 1770.6,
      "largest_segment_cm": 165.2,
      "segment_count": 24,
      "match_name_at_company": "Sara Helena Berg",
      "company_match_id": "",
      "notes": "Förväntad morbror-systerdotter-match.",
      "source_refs": []
    }
  ],

  "dna_segments": [
    {
      "id": "dna_segment_001",
      "dna_match_id": "dna_match_001_013",
      "company_id": "dna_company_myheritage",
      "chromosome": 7,
      "start_position": 45230000,
      "end_position": 68120000,
      "cm": 18.6,
      "snp_count": 3200
    }
  ],

  "dna_clusters": [
    {
      "id": "dna_cluster_001",
      "name": "Nära släkt - dokumenterad familj",
      "description": "DNA-träffar mellan huvudpersonen, föräldrar och systerdotter.",
      "company_ids": [
        "dna_company_myheritage"
      ],
      "person_ids": [
        "person_001",
        "person_005",
        "person_006",
        "person_013"
      ],
      "dna_match_ids": [
        "dna_match_001_005",
        "dna_match_001_006",
        "dna_match_001_013"
      ],
      "color": "#88aaee",
      "notes": ""
    }
  ],

  "dna_triangulations": [],

  "research_notes": [
    {
      "id": "note_001",
      "title": "Kommentar om exemplet",
      "text": "Detta är en fiktiv exempelfil. ID:n och källhänvisningar är påhittade.",
      "linked_entities": [
        {
          "entity_type": "person",
          "entity_id": "person_001"
        }
      ]
    }
  ]
}

The geneology folder should be something like:
My-family/
|- my-family.json.gz
|- my-family-settings.json (or other relevant format)
|- translation\
|   |- sources.json
|   |- places.json
|   |- persons.json
|- media\
|   |- source-image\
|   |- photos\
|   |- death-notice\
|   |- obituary\
|   |- funural-program\
|   |- grave-photo\
|   |- map\
|   |- logo\
|   |- document\

But with more added as needed

An alternative to the sources handling above, there could be repositories defined in a separate repository file with repositories like this:

"repositories": [
  {
    "id": "repo_arkivdigital",
    "name": "ArkivDigital",
    "type": "digital_archive",
    "address": null,
    "phone": [],
    "email": [],
    "web": ["https://www.arkivdigital.se"],
    "notes": "",
    "external_ids": []
  },
  {
    "id": "repo_riksarkivet",
    "name": "Riksarkivet",
    "type": "archive",
    "web": ["https://sok.riksarkivet.se"],
    "notes": ""
  }
]

And the source then actually looks something like this:

{
  "id": "source_birth_001",
  "provider": "ArkivDigital",
  "repository_refs": [
    {
      "repository_id": "repo_arkivdigital",
      "call_number": "Ljusdal C:6",
      "source_type": "Födelsebok",
      "image_number": 45,
      "page_number": 112,
      "media_type": "digital_image",
      "media_name": "Ljusdal C6 45 112.jpg",
      "notes": ""
    }
  ]
}

It is important that the datamodel can handle these things:
* One source can be the source of many different thing, place of birth, date of birth, father, mother etc
* Many sources can be the source for the same thing. Eg both Husförhörslängd and Födelsebok can be the source of the date of birth. So If one source is used and another better is found, you don't have to remove the first source, you can add another. But perhaps the first one only had date of birth, not the place.
* DNA connections (described separatly)
* Places so that if I want to filter on a specific parish, I should be able to do that even if there are more specific information in the place.
* a wide selection of events, and the information that is needed for each event type
* Needs to be able to handle both genetic family and legal family. Also need to be able to handle same sex marriges and insemination births.
* There needs to be information on the persons and relationships in the app-json, that makes sure every time the file is exported to gedcom, the exported files have the same ids for persons, regardless of how many new persons have been added or deleted in the file.
* A person shall be able to be part of several clusters at the same time.
* Each Cluster needs to be a separate entity in the file, and it shall be linked to each person in that cluster.
* An added photo should not only include the file name, but should have its own section, where it can be connected to many persons (family photo etc). It should also have a section for notes and one for a caption. On a wishlist I would like to be able to tag what person in the photo is which photo.

### DNA
DNA needs to have a few layers in the file.

* First there needs to be a test. The test has two different attachement points firm and individual. Also there need to be a note and an id field (where the id for the test at the test firm). Also should have a field about who handles the test.
* Then there should be a way to record matches for that test with other individuals. The file should contain information if it is a match between two tests recorded in the file or between one test in the file and one "external" test. It should have a field about the match quality in cM, % and number of segments and largetst segment.
* A person can have more than one test at a single firm, and tests at multiple firms.
* There should be a file with information about the firms (in the project folder), in that file there should be a firm_id, name, notes and a link to a logo for that firm, either directly or via a media_id.

suggestion:
{ "id": "dna_company_myheritage", "name": "MyHeritage", "logo_media_id": "media_logo_myheritage", "description": "DNA-företag med autosomala matchningar och segmentdata." }

for a test json format could be something like:
{ "id": "dna_profile_001", "person_id": "person_001", "company_id": "dna_company_myheritage", "test_type": "autosomal", "kit_name": "Erik Johan Lindström", "kit_id": "", "admin_person_id": "person_001", "admin_status": "self", "notes": "Huvudpersonens DNA-test." }

Suggestion for triangular matches:
{ "id": "dna_triangulation_001", "company_id": "dna_company_myheritage", "chromosome": 7, "overlap_start": 45600000, "overlap_end": 67900000, "segment_ids": [ "dna_segment_001", "dna_segment_002" ], "profile_ids": [ "dna_profile_001", "dna_profile_005", "dna_profile_099" ], "cluster_id": "dna_cluster_001", "notes": "Överlappande triangulerat segment." }

### Events
The following list of events for individuals need to be handled.

* adoption
* baptism
* birth
* blessing
* burial
* census
* confirmation
* cremation
* death
* emigration
* first_communion
* gender_correction
* graduation
* immigration
* name_change
* retirement
* will
* custom_individual_event

The following list of family events needs to be handled:

* divorce
* divorce_filed
* engagement
* marriage
* custom_family_event

Different events needs different fields in the data file. All events needs a date and a source, many needs a place. But for example a death needs a reason of death, while a marriage needs two persons to be married

### Relationship calculator
Should be able to calculate and show a graph of relationships between 2 persons. Both geneological relationships and relationships via spouses and adoptions/foster care children. Should be a choice if only geneological or both types are chosen, as well as only closesed or all relationships. Showable by both text and graph. 

## Python application

The python application needs to be able to present persons in three different standard views on the right side. On the left side there should be a list of persons in the file. Either the full list, or a filtred list.

1. Family view, with the person, its parents, its siblings, its parterns (and parents to their kids that has not been their partners) and the kids
2. Ancestry view, with parents, grandparents etc (possible to change depth in settings)
3. Descendants view, with kids, grandkids etc (same depth as in ancestry view)
The diagram views need to be zoomable.

The exact info presented in the person box should be changable in settings. Name, date of birth, place of birth, date of death, place of death, occupation, age and reason of death, together with photo should be possible to have in the person diagram. And in addition clusters and DNA-matches should be possible to have in the diagram. In the case of DNA-matches it should have a small logo for the company together with matches.

There needs to be a way to import a gedcom file and translate it to the app-json, using the translation files.
If there is already an app-json, it should try to update it with information from the new gedom file.
Unless the import already has an app-json, a main person for the file should be choosen.
There needs to be a way to export to a gedcom file. 

A person selected in the list changes active person directy. If a person is selected in the diagram, it should be possible to change that to the active person.

If a person is selected in the diagram view, a press of the button A should change active person to the selected person

If double clicking on a person in diagram view or in list, an edit window shall be opened (edit person window described in separate section)

### Edit Person view

The edit person view needs to be able to edit a few things. Preferably in separate tabs.
* First name, surename, surename at birth, title, occupation
* Events (list of events, add event, delete event) In each event, there shall be a possibility to add what source(s) have what information (exampel date and place may have different sources)
* A Photo list (and a way to add new photos and view photos) Here a main photo for diagram view should be possible to choose.
* A DNA and cluster section (Add/remove DNA connection to another persons DNA test and edit the numbers), (add/remove membership in a cluster)

### Edit objects
* Edit DNA test
* Edit cluster
* Edit title list
* Edit occupation list
* Edit place list
* Edit Source list
* Edit list of death reasons
* Edit photo list

### Printable graphs
All three kinds of basic graphs, as well as relationship graphs need to be printable

### First goals

* create base structure for python app folder
* Create a base structure for the project folder for a new geneology project
* Import gedcom file
* Save json.gz-file
* Edit source and place conversions, for future import.

### Limitations

Tests need to be with pytest

### Language rules

The program needs to be in Swedish

## Webb page

In a later stage, a read only webb app shall be constructed. The project needs to have that in mind, so it does not make limitations that makes this harder. The project folder should be possible to put on a folder outside of webb root and the webb app shall index it to be able to show relatives your research, without making it public to everyone.