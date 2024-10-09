import json

from flask import Flask, render_template, request, redirect

import ssnolib
from ssnolib import StandardNameTable, VectorStandardName
from ssnolib.qudt.utils import iri2str
from ssnolib.standard_name_table import ROLE2IRI

app = Flask(__name__)


@app.route('/')
def welcome():
    return render_template('welcome.html')


@app.route('/form', methods=['GET', 'POST'])
def form():
    return render_template('form.html', data={})


@app.route('/JSON-LD', methods=['POST'])
def json_ld():
    def parseAuthors(firstnames, lastNames, hadRoles, orcidIDs, mboxes):
        authors = []
        roles = []
        for (first_name, last_name, role, orcid, mbox) in zip(firstnames, lastNames, hadRoles, orcidIDs, mboxes):
            person_dict = dict(
                firstName=first_name if first_name != '' else None,
                lastName=last_name if last_name != '' else None,
                orcidId=orcid if orcid != '' else None,
                mbox=mbox if "@" in mbox else None
            )
            for k, v in person_dict.copy().items():
                if v is None:
                    person_dict.pop(k)
            authors.append(ssnolib.Person(**person_dict))
            roles.append(role)
        qualifiedAttributions = []
        for (role, author) in zip(roles, authors):
            if role:
                qualifiedAttributions.append(ssnolib.Attribution(agent=author, hadRole=ROLE2IRI[role.lower()]))
            else:
                qualifiedAttributions.append(ssnolib.Attribution(agent=author))
        return qualifiedAttributions

    def parseOrganizations(names, urls, rorIDs, hadRoles, mboxes):
        organizations = []
        roles = []
        for (name, url, rorID, role, mbox) in zip(names, urls, rorIDs, hadRoles, mboxes):
            organization_dict = dict(
                name=name if name != '' else None,
                url=url if url != '' else None,
                role=role if role != '' else None,
                mbox=mbox if "@" in mbox else None
            )
            for k, v in organization_dict.copy().items():
                if v is None:
                    organization_dict.pop(k)
            organizations.append(ssnolib.Organization(**organization_dict))
            roles.append(role)
        qualifiedAttributions = []
        for (role, organization) in zip(roles, organizations):
            if role:
                qualifiedAttributions.append(ssnolib.Attribution(agent=organization, hadRole=ROLE2IRI[role.lower()]))
            else:
                qualifiedAttributions.append(ssnolib.Attribution(agent=organization))
        return qualifiedAttributions

    qa_persons = parseAuthors(
        request.form.getlist("person.firstName[]"),
        request.form.getlist("person.lastName[]"),
        request.form.getlist("person.hadRole[]"),
        request.form.getlist("person.orcidId[]"),
        request.form.getlist("person.mbox[]"),
    )
    qa_orgas = parseOrganizations(
        request.form.getlist("organization.name[]"),
        request.form.getlist("organization.url[]"),
        request.form.getlist("organization.hasRorId[]"),
        request.form.getlist("organization.hadRole[]"),
        request.form.getlist("organization.mbox[]"),
    )
    qa_persons.extend(qa_orgas)
    snt = StandardNameTable(
        title=request.form.get("title"),
        version=request.form.get("version"),
        description=request.form.get("description"),
        qualifiedAttribution=qa_persons,
        # standardNames=[
        #     VectorStandardName(
        #         standardName=sn.get("name"),
        #         unit=sn.get("unit"),
        #         description=sn.get("description"),
        #     ) for sn in request.form.get("standardNames")
    )
    config_data = json.loads(snt.model_dump_jsonld())
    # Placeholder for the actual data retrieval logic
    # Here, we're using a dummy configuration for demonstration
    # config_data = {
    #     '@context': 'http://schema.org',
    #     '@type': 'StandardName',
    #     'title': 'Example Standard Name',
    #     'version': '1.0',
    #     'description': 'An example description of the standard name.',
    #     'authors': [
    #         {'@type': 'Person', 'name': 'John Doe'},
    #         {'@type': 'Person', 'name': 'Jane Smith'}
    #     ],
    #     'standardNames': [
    #         {'@type': 'DefinedTerm', 'name': 'Standard Name 1'},
    #         {'@type': 'DefinedTerm', 'name': 'Standard Name 2'}
    #     ]
    # }

    return render_template('jsonld.html', config_data=config_data)


@app.route('/loadJSONLD', methods=['POST'])
def loadJSONLD():
    # Get the uploaded file
    json_content = json.load(request.files['jsonld_file'])
    try:
        snt = ssnolib.parse_table(data=json_content)
        # snt = StandardNameTable.from_jsonld(data=json_content, limit=1)

        # Example of extracting data from JSON-LD
        if not isinstance(snt.qualifiedAttribution, list):
            if snt.qualifiedAttribution is not None:
                qualifiedAttribution = [snt.qualifiedAttribution]
            else:
                qualifiedAttribution = []
        else:
            if snt.qualifiedAttribution is not None:
                qualifiedAttribution = snt.qualifiedAttribution
            else:
                qualifiedAttribution = []

        persons = []
        organizations = []
        for qa in qualifiedAttribution:
            if isinstance(qa.agent, ssnolib.Person):
                persons.append(qa.agent.model_dump(exclude_none=True))
                if qa.hadRole:
                    persons[-1]["hadRole"] = qa.hadRole.rsplit("#", 1)[-1]
            elif isinstance(qa.agent, ssnolib.Organization):
                organizations.append(qa.agent.model_dump(exclude_none=True))
                if qa.hadRole:
                    organizations[-1]["hadRole"] = qa.hadRole.rsplit("#", 1)[-1]
        modifier = snt.hasModifier or []
        qualifications = [m for m in modifier if isinstance(m, (ssnolib.VectorQualification,
                                                                ssnolib.ScalarStandardName,
                                                                ssnolib.StandardName))]
        transformations = [m for m in modifier if isinstance(m, ssnolib.Transformation)]
        transformations_dict = [t.model_dump(exclude_none=True) for t in transformations]
        for i, transformation in enumerate(transformations):
            for j, character in enumerate(transformation.hasCharacter):
                if character.associatedWith.startswith('_:'):
                    for q in qualifications:
                        if q.id == character.associatedWith:
                            transformations_dict[i]["hasCharacter"][j]["associatedWith"] = q.name
                            break

        title = snt.title
        version = snt.version
        description = snt.description
        standard_names = snt.standardNames

        data = {
            'title': title,
            'version': version,
            'description': description,
            'persons': persons,
            'organizations': organizations,
            'qualifications': qualifications,
            'transformations': transformations_dict,
            'standard_names': [
                {'standardName': sn.standardName, 'unit_str': iri2str.get(sn.unit, 'N.A.'), 'unit': sn.unit,
                 'description': sn.description,
                 'is_vector': isinstance(sn, VectorStandardName)} for sn
                in standard_names]
        }

        # Render the form with pre-filled data
        return render_template('form.html', data=data)
    except Exception as e:
        pass
    # Redirect back to the welcome page if the file is not valid
    return redirect('/')


if __name__ == '__main__':
    app.run(debug=True)
